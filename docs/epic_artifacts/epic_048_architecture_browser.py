"""One-off architecture review witness; run from the repository root.

Creates an isolated fixture and starts only its read-only browsing server.
An optional path reuses that fixture and its pinned render cache.
"""
import sys,tempfile,shutil,time,json,re
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from tests.support import make_repo
from tests.war_room.test_architecture_browsing_browser_journey import _start,_stop,_commit,_wait_for_snapshot
from cascade.workspace import ProjectContext,resolve_design_ownership
from cascade.board.context import set_project_context
from playwright.sync_api import sync_playwright
source=Path.cwd()
if len(sys.argv)>1:
 root=Path(sys.argv[1]);proof=root.parent;project=ProjectContext.colocated(root);revision=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
else:
 source=Path.cwd(); proof=Path(tempfile.mkdtemp(prefix='epic048-browser-'));root=make_repo(proof)
 (root/'.gitignore').write_text('.cascade/\n__pycache__/\n')
 shutil.copytree(source/'cascade',root/'cascade',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copy2(source/'DESIGN.md',root/'DESIGN.md')
 project=ProjectContext.colocated(root);resolve_design_ownership(project,'.')
 project.editable_architecture_root.mkdir(parents=True,exist_ok=True)
 for n in ['model.dsl','views.dsl','workspace.dsl','workspace.contract.json']:
  shutil.copy2(source/'architecture/target-9f61bc6d6f8ae8cb7d196c8b327650d5'/n,project.editable_architecture_root/n)
 revision=_commit(root,'Exact recovery architecture browser fixture')
set_project_context(project)
server,thread,base=_start(root);report={'fixture':str(root),'fixture_revision':revision,'source_revision':__import__('subprocess').check_output(['git','rev-parse','HEAD'],text=True).strip(),'checks':[]}
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1500,'height':1100})
  started=time.monotonic();page.goto(base+'/?tab=architecture',wait_until='domcontentloaded');_wait_for_snapshot(page)
  report['initial_snapshot_load_seconds']=round(time.monotonic()-started,3)
  def select_view(key):
   view=page.locator('#architecture-view'); labels=view.locator('option').all_text_contents();i=next(i for i,x in enumerate(labels) if key in x);view.select_option(index=i)
  def explore(sid,key):
   node=page.locator('[aria-label="element '+sid+'"]');node.dispatch_event('dblclick')
   page.wait_for_function("key => document.querySelector('#architecture-view').value.includes(key)",arg=key)
   assert key in page.locator('#architecture-view').input_value()
  operations_before=json.loads((root/'.cascade/c4-render-operations.json').read_text())
  started=time.monotonic()
  for component,key,node,symbol,container in [
   ('agent','cascade-agent-code','agent.codex','run_codex_role','supervisor'),
   ('teams','cascade-teams-code','teams.validate_publish','check_and_publish_review_rebase','supervisor'),
   ('task-team','cascade-task-code','task.generation','admit_review_publication_generation','supervisor'),
   ('workspace-commands','cascade-workspace-commands-code','cli.status','_worker_supervisor_status','cli')]:
   select_view('cascade-context');explore('element.system.cascade','cascade-containers')
   explore('element.container.'+container,'cascade-supervisor-components' if container=='supervisor' else 'cascade-cli-components')
   explore('element.component.'+component,key)
   target='element.code.'+node;page.locator('[aria-label="element '+target+'"]').click()
   page.get_by_role('button',name='Open pinned source',exact=True).click()
   page.locator('#architecture-document-preview-body').filter(has_text='def '+symbol).wait_for(timeout=15000)
   url=page.url;page.reload(wait_until='domcontentloaded');_wait_for_snapshot(page,timeout=30000)
   assert key in page.locator('#architecture-view').input_value()
   assert page.locator('[aria-label="element '+target+'"]').get_attribute('aria-pressed')=='true'
   # Selection back, then semantic level up.
   page.locator('#architecture-back').click()
   if key in page.locator('#architecture-view').input_value():page.locator('#architecture-back').click()
   assert ('components' in page.locator('#architecture-view').input_value()),page.locator('#architecture-view').input_value()
   report['checks'].append({'view':key,'pinned_symbol':symbol,'deep_link':url,'level_up':True})
  assert json.loads((root/'.cascade/c4-render-operations.json').read_text())==operations_before
  report['warm_artifact_reused']=True
  report['warm_four_journeys_seconds']=round(time.monotonic()-started,3)
  page.screenshot(path=str(proof/'navigation.png'))
  browser.close()
 report['status']='passed'
except Exception as e:
 report['status']='failed';report['error']=repr(e)
 try: report['ui']=page.locator('body').inner_text()[-10000:];page.screenshot(path=str(proof/'failure.png'))
 except Exception:pass
 raise
finally:
 (proof/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True);_stop(server,thread);set_project_context(None)
