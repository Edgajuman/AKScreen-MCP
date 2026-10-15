import io
import json
import os
import socket
import subprocess
import sys
import threading
import unittest
from unittest import mock

from ak_screen_mcp.bridge import Bridge, BridgeError
from ak_screen_mcp.server import handle, serve
from ak_screen_mcp.tools import Tools


class FakeEditor:
    def __init__(self):
        self.calls = []
    def call(self, method, params=None):
        self.calls.append((method, params))
        if method == 'engine.commands':
            return [{'id':'effects.apply','label':'Apply effect','enabled':True}, {'id':'file.save','enabled':False}]
        return {'method':method,'params':params}
    def execute(self, command, params=None):
        self.calls.append((command, params))
        if command == 'bad':
            raise BridgeError('Invalid edit')
        return {'id':command}


class McpTests(unittest.TestCase):
    def setUp(self):
        self.editor = FakeEditor()
        self.tools = Tools(self.editor)

    def test_handshake_and_discovery_do_not_require_the_editor_to_be_open(self):
        response = handle(dict(jsonrpc='2.0', id=1, method='initialize',params={'protocolVersion':'2025-06-18'}), self.tools)
        self.assertEqual(response['result']['protocolVersion'],'2025-06-18')
        self.assertEqual(self.editor.calls,[])
        tools = handle(dict(jsonrpc='2.0',id=2,method='tools/list'),self.tools)['result']['tools']
        self.assertGreaterEqual(len(tools),9)
        self.assertTrue(all(t['inputSchema']['type']=='object' for t in tools))

    def test_notifications_produce_no_reply_and_bad_requests_are_recoverable(self):
        self.assertIsNone(handle(dict(jsonrpc='2.0',method='notifications/initialized'),self.tools))
        self.assertEqual(handle([],self.tools)['error']['code'],-32600)
        incoming=io.BytesIO(b'not-json\n{"jsonrpc":"2.0","id":9,"method":"ping"}\n')
        output=io.StringIO();serve(self.tools,incoming,output)
        replies=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(replies[0]['error']['code'],-32700)
        self.assertEqual(replies[1]['id'],9)

    def test_discovery_filters_and_batch_stops_without_repeating_mutations(self):
        self.assertEqual(len(self.tools.call('command_list',dict(filter='effects',enabled_only=True))),1)
        result=self.tools.call('command_batch',dict(steps=[dict(id='first'),dict(id='bad'),dict(id='third')]))
        self.assertEqual(result['completed'],1)
        self.assertEqual(result['failed'],1)
        self.assertNotIn(('third',{}),self.editor.calls)
        self.assertEqual([call[0] for call in self.editor.calls].count('first'),1)

    def test_invalid_mutation_arguments_and_oversized_batches_are_refused(self):
        for arguments in [dict(steps=[]),dict(steps=[dict(id='x')]*51),dict(steps=[dict(id='x',params=[])]),dict(steps=[[]])]:
            with self.assertRaises(BridgeError):self.tools.call('command_batch',arguments)
        with self.assertRaises(BridgeError):self.tools.call('ui_control',dict(action='arbitrary-shell',params={}))

    def test_bridge_authentication_id_and_long_export_flags(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        received=[]
        def editor():
            with listener:
                connection,_=listener.accept()
                with connection:
                    stream=connection.makefile('rb');request=json.loads(stream.readline())
                    received.append(request)
                    connection.sendall((json.dumps(dict(id=request['id'],ok=True,result={'job':7}))+'\n').encode())
        thread=threading.Thread(target=editor);thread.start()
        bridge=Bridge(listener.getsockname()[1],'x'*43)
        self.assertEqual(bridge.execute('file.exportMedia',{'wait':True})['job'],7)
        thread.join(timeout=2)
        self.assertEqual(received[0]['params']['_ak_token'],'x'*43)
        self.assertFalse(received[0]['params']['params']['wait'])

    def test_bridge_rejects_invalid_ports_and_short_tokens(self):
        for port in [0,65536,False,-1]:
            with self.assertRaises(ValueError):Bridge(port,'x'*43)
        with self.assertRaises(ValueError):Bridge(9876,'short')
        for token in [None,'x'*42+'\n','x'*42+' ','x'*42+'é']:
            with self.assertRaises(ValueError):Bridge(9876,token)

    def test_lost_mutation_reply_is_not_retried(self):
        connection=mock.MagicMock()
        connection.__enter__.return_value=connection
        connection.makefile.return_value.__enter__.return_value.readline.return_value=b''
        with mock.patch('socket.create_connection',return_value=connection) as connect:
            with self.assertRaisesRegex(BridgeError,'inspect the project'):
                Bridge(9876,'x'*43).execute('sequence.addEdit')
            self.assertEqual(connect.call_count,1)
            self.assertEqual(connection.sendall.call_count,1)

    def test_real_stdio_process_accepts_handshake_without_touching_editor(self):
        environment=dict(os.environ,AKSCREEN_CONTROL_TOKEN='x'*43)
        request=json.dumps(dict(jsonrpc='2.0',id=17,method='initialize',params={'protocolVersion':'2025-11-25'}))+'\n'
        process=subprocess.run([sys.executable,'-m','ak_screen_mcp.server'],input=request,text=True,capture_output=True,env=environment,timeout=10)
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(json.loads(process.stdout)['id'],17)
        self.assertNotIn(environment['AKSCREEN_CONTROL_TOKEN'],process.stdout+process.stderr)

    def test_deep_json_is_rejected_and_the_next_request_still_works(self):
        incoming=io.BytesIO(b'['*2000+b'0'+b']'*2000+b'\n{"jsonrpc":"2.0","id":3,"method":"ping"}\n')
        output=io.StringIO();serve(self.tools,incoming,output)
        replies=[json.loads(line) for line in output.getvalue().splitlines()]
        # Python versions differ in decoder depth limits: both a parse rejection
        # and a parsed array rejected as an invalid JSON-RPC request are correct.
        self.assertIn(replies[0]['error']['code'],(-32700,-32600))
        self.assertEqual(replies[1]['id'],3)

    def test_tool_errors_are_structured_and_do_not_crash_the_session(self):
        reply=handle(dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name='command_run',arguments=dict(id='bad'))),self.tools)
        self.assertTrue(reply['result']['isError'])
        self.assertIn('Invalid edit',reply['result']['content'][0]['text'])
        self.assertEqual(handle(dict(jsonrpc='2.0',id=2,method='ping'),self.tools)['result'],{})


if __name__=='__main__':unittest.main()
