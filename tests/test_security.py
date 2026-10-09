"""Public security regressions. Every resource and file is synthetic and temporary."""
import concurrent.futures,hashlib,io,json,os,sqlite3,stat,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from agent_browser_coordinator import coordinator as core
from scripts import package_release,release_files,verify_install,verify_backup
from agent_browser_coordinator.coordinator import Coordinator,Conflict
ROOT=Path(__file__).resolve().parents[1]
class Security(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='abc-security-');self.root=Path(self.temp.name)
  self.db=self.root/'state.db';self.co=Coordinator(self.db,lambda:1000.0);self.co.initialize('synthetic-ui',True)
 def tearDown(self):self.temp.cleanup()
 def sql(self,query):
  with sqlite3.connect(self.db) as c:return c.execute(query).fetchall()
 def cli(self,*args):
  return subprocess.run([sys.executable,str(ROOT/'src/agent_browser_coordinator/coordinator.py'),'--db',str(self.db),*args],capture_output=True,text=True,timeout=15,env=verify_install.minimal_environment())
 def test_unknown_payload_is_rejected_and_not_persisted(self):
  with self.assertRaises(Conflict):self.co.execute('acquire','bad-extra','worker',unneeded_private_value='synthetic-sensitive')
  self.assertEqual(self.sql('SELECT COUNT(*) FROM requests')[0][0],0)
  self.assertNotIn('synthetic-sensitive',self.db.read_bytes().decode('latin1'))
 def test_boolean_revision_is_rejected(self):
  self.co.execute('freeze','freeze','operator')
  with self.assertRaises(Conflict):self.co.execute('recover','bad-revision','operator',expected_revision=True,expected_token=None,expected_shutdown_token=None,verified_idle=True,old_worker_quiescent=True,evidence='synthetic')
  self.assertTrue(self.co.status()['frozen'])
 def test_bool_instead_of_token_and_list_tab_rejected(self):
  for kwargs in [{'token':True,'action':'one'},{'token':'opaque','tab':[],'action':'two'}]:
   with self.subTest(kwargs=kwargs),self.assertRaises(Conflict):self.co.execute('close-begin' if 'tab' in kwargs else 'begin','bad-types','worker',**kwargs)
 def test_invalid_boolean_argument_rejected(self):
  with self.assertRaises(Conflict):self.co.execute('inventory','bad-bool','worker',token='opaque',complete=1)
 def test_duplicate_json_key_cli_rejected(self):
  r=self.cli('acquire','--actor','worker','--request','dup','--args','{"priority":10,"priority":20}')
  self.assertEqual(r.returncode,2);self.assertFalse(json.loads(r.stdout)['ok']);self.assertIsNone(self.co.status()['owner'])
 def test_nonfinite_json_cli_rejected(self):
  for value in ['NaN','Infinity','-Infinity']:
   with self.subTest(value=value):
    r=self.cli('acquire','--actor','worker','--request','nonfinite','--args','{"priority":'+value+'}')
    self.assertEqual(r.returncode,2);self.assertIsNone(self.co.status()['owner'])
 def test_non_object_json_cli_rejected(self):
  r=self.cli('acquire','--actor','worker','--request','array','--args','[]')
  self.assertEqual(r.returncode,2);self.assertFalse(json.loads(r.stdout)['ok'])
 def test_oversize_json_cli_rejected(self):
  r=self.cli('acquire','--actor','worker','--request','large','--args',json.dumps({'unknown':'x'*17000}))
  self.assertEqual(r.returncode,2);self.assertEqual(self.sql('SELECT COUNT(*) FROM requests')[0][0],0)
 def test_invalid_clock_init_creates_no_file(self):
  for i,value in enumerate([float('nan'),float('inf'),float('-inf'),True,None]):
   p=self.root/f'bad-clock-{i}.db'
   with self.subTest(value=value),self.assertRaises(Conflict):Coordinator(p,lambda:value).initialize('mock',True)
   self.assertFalse(p.exists())
 def test_invalid_clock_status_fails_closed(self):
  for value in [float('nan'),float('inf'),True]:
   with self.subTest(value=value),self.assertRaises(Conflict):Coordinator(self.db,lambda:value).status()
 def test_invalid_clock_command_cannot_change_state(self):
  with self.assertRaises(Conflict):Coordinator(self.db,lambda:float('nan')).execute('acquire','bad-time','worker')
  self.assertEqual(self.sql('SELECT COUNT(*) FROM requests')[0][0],0);self.assertIsNone(self.co.status()['owner'])
 def test_boolean_schema_is_corrupt_not_version_one(self):
  body=json.loads(self.sql('SELECT body FROM state')[0][0]);body['schema']=True
  with sqlite3.connect(self.db) as c:c.execute('UPDATE state SET body=?',(json.dumps(body),))
  with self.assertRaises(Conflict):self.co.status()
 def test_db_symlink_is_rejected_without_audit_write(self):
  link=self.root/'alias.db';link.symlink_to(self.db);before=self.db.read_bytes()
  with self.assertRaises(Conflict):Coordinator(link).execute('acquire','bad-link','worker')
  self.assertEqual(self.db.read_bytes(),before);self.assertEqual(self.sql('SELECT COUNT(*) FROM rejections')[0][0],0)
 def test_dangling_db_symlink_does_not_create_target(self):
  target=self.root/'absent.db';link=self.root/'alias.db';link.symlink_to(target)
  with self.assertRaises(Conflict):Coordinator(link).initialize('mock',True)
  self.assertFalse(target.exists())
 def test_db_parent_symlink_rejected(self):
  actual=self.root/'actual';actual.mkdir();alias=self.root/'alias';alias.symlink_to(actual,target_is_directory=True)
  with self.assertRaises(Conflict):Coordinator(alias/'new.db').initialize('mock',True)
  self.assertFalse((actual/'new.db').exists())
 def test_shared_writable_db_parent_rejected(self):
  parent=self.root/'unsafe';parent.mkdir(mode=0o777);parent.chmod(0o777)
  with self.assertRaises(Conflict):Coordinator(parent/'new.db').initialize('mock',True)
 def test_db_hardlink_rejected(self):
  link=self.root/'hard.db';os.link(self.db,link)
  with self.assertRaises(Conflict):Coordinator(link).status()
 def test_db_file_created_private(self):
  self.assertEqual(stat.S_IMODE(self.db.stat().st_mode),0o600)
 def test_db_identity_swap_detected_before_transaction(self):
  real=sqlite3.connect;swapped=False;replacement=b'unchanged replacement'
  def connect(*a,**k):
   nonlocal swapped
   c=real(*a,**k)
   if not swapped:
    swapped=True;self.db.rename(self.root/'old.db');self.db.write_bytes(replacement)
   return c
  with patch.object(core.sqlite3,'connect',side_effect=connect),self.assertRaises(Conflict):self.co.status()
  self.assertEqual(self.db.read_bytes(),replacement)
 def test_dashboard_cannot_overwrite_database(self):
  before=self.db.read_bytes();r=self.cli('dashboard','--output',str(self.db))
  self.assertEqual(r.returncode,2);self.assertEqual(self.db.read_bytes(),before);self.assertIsNone(self.co.status()['owner'])
 def test_dashboard_cannot_overwrite_existing_output(self):
  out=self.root/'snapshot.html';out.write_text('preserve')
  with self.assertRaises(FileExistsError):core.write_dashboard(out,'replacement')
  self.assertEqual(out.read_text(),'preserve')
 def test_dashboard_symlink_and_parent_symlink_rejected(self):
  out=self.root/'original';out.write_text('preserve');link=self.root/'link';link.symlink_to(out)
  with self.assertRaises(Conflict):core.write_dashboard(link,'bad')
  actual=self.root/'actual';actual.mkdir();alias=self.root/'alias';alias.symlink_to(actual,target_is_directory=True)
  with self.assertRaises(Conflict):core.write_dashboard(alias/'out','bad')
  self.assertEqual(out.read_text(),'preserve');self.assertFalse((actual/'out').exists())
 def test_dashboard_exclusive_race_has_one_winner(self):
  out=self.root/'new.html'
  def write(value):
   try:core.write_dashboard(out,value);return True
   except FileExistsError:return False
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,['one','two']))
  self.assertEqual(sum(results),1);self.assertIn(out.read_text(),['one','two']);self.assertEqual(stat.S_IMODE(out.stat().st_mode),0o600)
 def test_wrong_actor_or_old_token_cannot_begin(self):
  t=self.co.execute('acquire','a','worker')['owner']['token']
  with self.assertRaises(Conflict):self.co.execute('begin','forged-actor','other',token=t,action='bad')
  self.co.execute('release','r','worker',token=t,safe=True)
  self.co.execute('acquire','b','worker')
  with self.assertRaises(Conflict):self.co.execute('begin','stale-token','worker',token=t,action='bad')
 def test_actor_labels_are_not_authentication(self):
  token=self.co.execute('acquire','a','worker')['owner']['token']
  # A second trusted client with the SAME label and token is indistinguishable.
  # This deliberately documents the boundary; never expose this API to hostile actors.
  other_client=Coordinator(self.db,lambda:1000.0)
  r=other_client.execute('begin','same-label','worker',token=token,action='synthetic')
  self.assertEqual(r['active']['actor'],'worker')
 def test_release_builder_refuses_existing_zip_and_checksum(self):
  source=self.root/'source';source.mkdir();(source/'file.txt').write_text('source');dest=self.root/'out';dest.mkdir()
  for suffix in ['-source.zip','-source.zip.sha256']:
   target=dest/('agent-browser-coordinator-'+core.VERSION+suffix);target.write_text('preserve')
   with patch.object(package_release,'ROOT',source),patch.object(package_release,'FILES',['file.txt']),self.assertRaises(ValueError):package_release.build(dest)
   self.assertEqual(target.read_text(),'preserve');target.unlink()
 def test_release_builder_refuses_symlink_destination(self):
  actual=self.root/'actual';actual.mkdir();alias=self.root/'dist';alias.symlink_to(actual,target_is_directory=True)
  source=self.root/'source';source.mkdir();(source/'file.txt').write_text('source')
  with patch.object(package_release,'ROOT',source),patch.object(package_release,'FILES',['file.txt']),self.assertRaises(ValueError):package_release.build(alias)
  self.assertEqual(list(actual.iterdir()),[])
 def test_source_intermediate_symlink_rejected(self):
  outside=self.root/'outside';outside.mkdir();(outside/'one').write_text('outside');source=self.root/'source';source.mkdir();(source/'link').symlink_to(outside,target_is_directory=True)
  with self.assertRaises(ValueError):release_files.safe_read(source,'link/one')
 def test_source_symlink_swap_rejected(self):
  source=self.root/'source';source.mkdir();p=source/'one';p.write_text('source');outside=self.root/'outside';outside.write_text('outside');real=os.open
  def swapped(path,flags,*a,**kw):
   if Path(path)==p and not p.is_symlink():p.unlink();p.symlink_to(outside)
   return real(path,flags,*a,**kw)
  with patch.object(release_files.os,'open',side_effect=swapped),self.assertRaises(OSError):release_files.safe_read(source,'one')
  self.assertEqual(outside.read_text(),'outside')
 def test_restore_parent_symlink_rejected(self):
  actual=self.root/'actual';actual.mkdir();alias=self.root/'alias';alias.symlink_to(actual,target_is_directory=True)
  with self.assertRaises(ValueError):verify_backup.restore(self.root/'unused.zip','0'*64,alias/'new')
  self.assertEqual(list(actual.iterdir()),[])
 def test_bad_wheel_hash_executes_nothing(self):
  wheel=self.root/('agent_browser_coordinator-'+core.VERSION+'-py3-none-any.whl');wheel.write_bytes(b'not a wheel')
  with patch.object(verify_install.subprocess,'run') as run,self.assertRaises(ValueError):verify_install.verify(wheel,'0'*64)
  run.assert_not_called()
 def test_wheel_subprocess_environment_excludes_credentials_and_optimization(self):
  with patch.dict(os.environ,{'GH_TOKEN':'synthetic-only','PYTHONOPTIMIZE':'1','PIP_CONFIG_FILE':'synthetic-only','GH_CONFIG_DIR':'synthetic-only'}):
   result=verify_install.minimal_environment()
  self.assertEqual(set(result),{'PATH','LANG','LC_ALL'})
 def test_wheel_subprocess_has_timeout_and_minimal_env(self):
  with patch.object(verify_install.subprocess,'run',return_value=subprocess.CompletedProcess([],0)) as run:verify_install.run(['synthetic'])
  self.assertEqual(run.call_args.kwargs['timeout'],120);self.assertEqual(set(run.call_args.kwargs['env']),{'PATH','LANG','LC_ALL'})
 def test_verification_rejects_optimized_python(self):
  r=subprocess.run([sys.executable,'-O','-m','scripts.validate_release'],capture_output=True,text=True,timeout=15)
  self.assertNotEqual(r.returncode,0)
 def test_release_gate_existing_output_exits_nonzero_without_overwrite(self):
  out=self.root/'existing';out.mkdir();marker=out/'keep';marker.write_text('preserve')
  r=subprocess.run([sys.executable,'-m','scripts.release_gate','--output-dir',str(out)],capture_output=True,text=True,timeout=15,env=verify_install.minimal_environment())
  self.assertNotEqual(r.returncode,0);self.assertFalse(json.loads(r.stdout)['ok']);self.assertEqual(marker.read_text(),'preserve')
 def test_release_gate_required_command_failure_propagates(self):
  from scripts import release_gate
  with self.assertRaises(RuntimeError):release_gate.checked([sys.executable,'-c','raise SystemExit(7)'],self.root,timeout=10)
 def test_read_only_arguments_and_exponent_overflow_rejected(self):
  for args in ['{"unused":"synthetic"}','{"unused":1e999}','{"unused":[{"nested":-1e999}]}']:
   with self.subTest(args=args):
    r=self.cli('status','--args',args)
    self.assertEqual(r.returncode,2);self.assertFalse(json.loads(r.stdout)['ok'])
 def test_unused_global_cli_flags_rejected(self):
  for args in [('status','--actor','unused'),('acquire','--actor','a','--request','a','--output','unused')]:
   with self.subTest(args=args):self.assertEqual(self.cli(*args).returncode,2)
 def test_wheel_distribution_metadata_mismatch_executes_nothing(self):
  wheel=self.root/('agent_browser_coordinator-'+core.VERSION+'-py3-none-any.whl')
  with zipfile.ZipFile(wheel,'w') as z:z.writestr('agent_browser_coordinator-'+core.VERSION+'.dist-info/METADATA','Name: agent-browser-coordinator\nVersion: 0.0.0\n')
  expected=hashlib.sha256(wheel.read_bytes()).hexdigest()
  with patch.object(verify_install.subprocess,'run') as run,self.assertRaises(ValueError):verify_install.verify(wheel,expected)
  run.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
