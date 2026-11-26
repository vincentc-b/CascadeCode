"""Owned planning smoke: run with PYTHONPATH=. from the epic checkout.

Requires the already verified local renderer and Playwright; installs nothing.
Only unrelated operational-panel requests are stubbed; architecture requests
use the production HTTP routes and real renderer. Results stay in .cascade/.
"""
from pathlib import Path
import json,time,threading
from playwright.sync_api import sync_playwright
from cascade.board.context import set_project_context
from cascade.workspace import ProjectContext
from cascade.workspace.types import RepositoryContext
from cascade.workspace.integration_worktree import locate_trunk
from cascade.war_room.server import serve
root=Path.cwd(); canonical=ProjectContext.colocated(locate_trunk(root))
repo=RepositoryContext(root=root,repository_key=canonical.target.repository_key);set_project_context(ProjectContext(repo,repo))
server=serve(root=root,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
result={'paths':[], 'http_errors':[]};started=time.monotonic()
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1100});page.set_default_timeout(20000)
  page.on('response',lambda response: result['http_errors'].append({'url':response.url,'status':response.status}) if '/api/architecture/' in response.url and response.status>=400 else None)
  # Keep the operational board and unrelated teams out of this architecture-only check.
  page.route('**/api/**',lambda route: route.continue_() if '/api/architecture/' in route.request.url else route.fulfill(status=200,content_type='application/json',body='{}'))
  print(base,flush=True)
  page.goto(base+'/?tab=architecture',wait_until='domcontentloaded')
  page.locator('#architecture-ready:not([hidden])').wait_for(timeout=210000)
  page.locator('#architecture-viewer .semantic-c4-svg').wait_for()
  result['initial_ready_seconds']=time.monotonic()-started
  ledger=root/'.cascade/c4-render-operations.json'
  before=json.loads(ledger.read_text());result['render_operations_before']=len(before.get('operations',{}))
  view=page.locator('#architecture-view')
  def select_view(key):
   options=view.locator('option');idx=next(i for i,t in enumerate(options.all_text_contents()) if key in t)
   view.select_option(index=idx)
   page.locator('#architecture-viewer .semantic-c4-svg').wait_for()
  def target(sid):
   page.locator(f'[aria-label="element {sid}"]').click()
  for container,component,cv,node,symbol in [
   ('supervisor','watchdog','cascade-watchdog-code','element.code.watchdog.review-health','reconcile_open_review_health'),
   ('supervisor','boss','cascade-boss-code','element.code.boss.review-pending','feature_review_pending'),
   ('supervisor','workspace','cascade-workspace-code','element.code.workspace.delivery-locked','_run_queue_delivery_locked')]:
   tick=time.monotonic();select_view('cascade-context');target('element.system.cascade');assert 'cascade-containers' in view.input_value()
   target('element.container.'+container)
   # Supervisor exposes a focused team view as another destination; use the real chooser when shown.
   if 'components' not in view.input_value():
    page.locator('#architecture-drill-choices button').filter(has_text='cascade-supervisor-components').click()
   target('element.component.'+component)
   if cv not in view.input_value():
    page.locator('#architecture-drill-choices button').filter(has_text=cv).click()
   assert cv in view.input_value(),view.input_value()
   target(node);deep=page.url
   assert 'target='+node in deep and 'view='+cv in deep
   page.reload(wait_until='domcontentloaded');page.locator('#architecture-ready:not([hidden])').wait_for(timeout=30000)
   assert page.locator(f'[aria-label="element {node}"]').get_attribute('aria-pressed')=='true'
   page.locator('#architecture-target-detail button',has_text='Open pinned source').click()
   preview=page.locator('#architecture-document-preview-body');preview.filter(has_text='def '+symbol).wait_for()
   assert 'def '+symbol in preview.inner_text()
   page.locator('#architecture-back').click();assert 'components' in view.input_value()
   result['paths'].append({'component':component,'view':cv,'node':node,'symbol':symbol,'deep_link_restored':True,'pinned_source_opened':True,'level_up':True,'elapsed_seconds':time.monotonic()-tick})
  after=json.loads(ledger.read_text());result['render_operations_after']=len(after.get('operations',{}))
  assert result['render_operations_after']==result['render_operations_before']
  assert not result['http_errors'],result['http_errors']
  result['provenance']=page.locator('#architecture-provenance-list').inner_text()
  browser.close()
finally:
 server.shutdown();server.server_close();thread.join(timeout=5);set_project_context(None)
 result['total_seconds']=time.monotonic()-started
 (root/'.cascade/epic051-browser.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result,indent=2),flush=True)
