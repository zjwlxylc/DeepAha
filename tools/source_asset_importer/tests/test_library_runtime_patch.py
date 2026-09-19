"""Real subprocess/loopback tests with a synthetic Codex, not a cloud account."""
import json, sys, tempfile, threading, time, unittest
from pathlib import Path
from unittest.mock import patch
from deepaha_importer.codex_process import CodexProcess, CodexLibraryConfig
from deepaha_importer.errors import ImporterError

FAKE = r'''
import json,sys,time
from pathlib import Path
args=sys.argv[1:]
if '--version' in args:print('codex-cli 1.0-test');sys.exit(0)
if '--help' in args:print('--json --output-schema --output-last-message --skip-git-repo-check --sandbox');sys.exit(0)
if 'login' in args:print('Logged in using ChatGPT hidden-account@example.com');sys.exit(0)
if 'features' in args:print('apps stable true');sys.exit(0)
print(json.dumps({'type':'turn.started'}),flush=True)
if Path('wait.flag').exists():time.sleep(30)
if Path('failure.flag').exists():
 print(json.dumps({'type':'turn.failed','error':{'message':'Rate limit exceeded sk-SECRET'}}),flush=True)
 print('429 rate limit sk-SECRET private@example.com',file=sys.stderr);sys.exit(4)
payload=json.loads(sys.stdin.read())
Path(args[args.index('--output-last-message')+1]).write_text(json.dumps(payload))
print(json.dumps({'type':'item.completed','item':{'type':'mcp_tool_call','server':'synthetic-files','tool':'list','status':'completed','result':{'content':[]}}}),flush=True)
print(json.dumps({'type':'turn.completed'}),flush=True)
'''
class RuntimeTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
  self.script=self.root/'fake_cli.py';self.script.write_text(FAKE);self.work=self.root/'work';self.work.mkdir()
  self.prefix=patch('deepaha_importer.codex_process._executable_prefix',return_value=[sys.executable,str(self.script)])
  self.prefix.start();self.addCleanup(self.prefix.stop)
  self.p=CodexProcess(CodexLibraryConfig(timeout_seconds=30))
 def test_real_process_preflight_without_ephemeral(self):
  p=self.p;out=p.preflight(threading.Event())
  self.assertEqual(out['status'],'CODEX_READY_LIBRARY_UNVERIFIED');self.assertFalse(p.supports_ephemeral)
  result,tools=p.run('{"ok":true}',{},self.work,'list',threading.Event())
  self.assertTrue(result['ok']);self.assertEqual(len(tools),1)
  self.assertNotIn('hidden-account',json.dumps(out));self.assertEqual(p.last_diagnostic['exit_code'],0)
 def test_real_process_cancel_is_bounded(self):
  (self.work/'wait.flag').touch();cancel=threading.Event();timer=threading.Timer(.3,cancel.set);timer.start()
  start=time.monotonic()
  try:
   with self.assertRaises(ImporterError) as caught:self.p.run('{}',{},self.work,'list',cancel)
  finally:timer.cancel()
  self.assertEqual(caught.exception.code,'LIBRARY_CANCELLED');self.assertLess(time.monotonic()-start,5)
  self.assertFalse((self.work/'result.json').exists())
 def test_safe_failure_classification_preserves_no_error_text(self):
  (self.work/'failure.flag').touch()
  with self.assertRaises(ImporterError):self.p.run('{}',{},self.work,'list',threading.Event())
  diag=self.p.last_diagnostic
  self.assertEqual(diag.get('failure_category'),'RATE_LIMIT')
  self.assertNotIn('SECRET',json.dumps(diag));self.assertNotIn('private@',json.dumps(diag))
  self.assertIn('turn.failed',diag['observed_event_types'])
 def test_metadata_cancel_before_start_never_launches(self):
  cancel=threading.Event();cancel.set()
  with patch('deepaha_importer.codex_process.subprocess.Popen',side_effect=AssertionError('cancelled command was launched')) as call:
   with self.assertRaises(ImporterError):self.p._metadata_command([sys.executable],['--version'],cancel)
   call.assert_not_called()
