"""The project comparison uses the same visible change colors on both sides."""
from pathlib import Path

import pytest


def test_project_change_colors_and_selection_in_native_svg():
    playwright = pytest.importorskip('playwright.sync_api')
    assets = Path(__file__).parents[2] / 'cascade/war_room/static'
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f'Chromium unavailable: {exc}')
        try:
            page = browser.new_page()
            page.set_content('<main><div id="current"></div><div id="proposed"></div></main>')
            page.add_style_tag(path=str(assets / 'plan_viewer.css'))
            page.add_script_tag(path=str(assets / 'plan_viewer.js'))
            colors = page.evaluate('''async () => {
              const targets = {
                current: [['gone', 'removed'], ['edited', 'changed'], ['stable', 'unchanged'], ['edge', 'changed', 'relationship']],
                proposed: [['new', 'added'], ['edited', 'changed'], ['stable', 'unchanged'], ['edge', 'changed', 'relationship']],
              };
              const viewers = {};
              for (const side of ['current', 'proposed']) {
                const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100" style="width:4000px;height:1000px">' +
                  targets[side].map(([id, state, kind], index) =>
                    '<g data-cascade-semantic-id="' + id + '" data-cascade-model-kind="' + (kind || 'element') + '">' +
                    '<rect joint-selector="body" x="' + (10 + index * 120) + '" y="10" width="100" height="70" fill="white" stroke="black"/>' +
                    '</g>').join('') + '</svg>';
                viewers[side] = PlanViewer.createSemanticC4Viewer({
                  document, container: document.getElementById(side), sideName: side,
                  side: { svg, targets: targets[side].map(([semantic_id, state, kind]) => ({kind: kind || 'element', semantic_id, state})) },
                });
                await viewers[side].ready;
              }
              const read = (side, id) => {
                const hit = document.querySelector('#' + side + ' [data-cascade-semantic-id="' + id + '"]');
                const css = getComputedStyle(hit);
                return { state: hit.dataset.cascadeDiffState, outline: css.outlineColor, filter: css.filter, stroke: getComputedStyle(hit.querySelector('rect')).stroke };
              };
              const result = { removed: read('current', 'gone'), added: read('proposed', 'new'),
                before: read('current', 'edited'), after: read('proposed', 'edited'), edgeBefore: read('current', 'edge'), edgeAfter: read('proposed', 'edge') };
              viewers.proposed.selectTarget('element', 'edited');
              result.selected = read('proposed', 'edited');
              return result;
            }''')
            assert page.locator('#current svg').evaluate('(svg) => svg.getBoundingClientRect().width <= svg.parentElement.getBoundingClientRect().width')
            assert page.locator('#proposed svg').evaluate('(svg) => svg.style.width') == ''
            assert colors['edgeBefore']['stroke'] == colors['edgeAfter']['stroke'] == 'rgb(191, 135, 0)'
            assert colors['removed']['outline'] == 'rgb(207, 34, 46)'
            assert colors['added']['outline'] == 'rgb(35, 134, 54)'
            assert colors['before']['outline'] == colors['after']['outline'] == 'rgb(191, 135, 0)'
            assert 'rgb(191, 135, 0)' in colors['selected']['filter']
            assert page.locator('#current [data-cascade-diff-state="added"]').count() == 0
            assert page.locator('#proposed [data-cascade-diff-state="removed"]').count() == 0
        finally:
            browser.close()


def test_service_drills_to_component_overview_and_exposes_distinct_choices():
    playwright = pytest.importorskip('playwright.sync_api')
    assets = Path(__file__).parents[2] / 'cascade/war_room/static'
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f'Chromium unavailable: {exc}')
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 720})
            page.set_content('<main></main>')
            page.add_style_tag(path=str(assets / 'plan_viewer.css'))
            page.add_script_tag(path=str(assets / 'plan_viewer.js'))
            setup = '''(ambiguous) => {
              document.body.innerHTML = '<div style="height:1500px"></div><main><section id="review"></section></main><div style="height:1500px"></div>';
              const target = id => ({kind:'element',semantic_id:id,label:id,state:'unchanged'});
              const choices = [
                {view_key:'overview',level:'componentViews',scope_id:'service',label:'All service components'},
                {view_key:'focused',level:'componentViews',scope_id:'service',label:'Team components'},
              ];
              const side = targets => ({revision:'revision',repository_key:'repo',targets,
                svg:'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 100">' +
                  targets.map((t,i)=>'<g data-cascade-model-kind="element" data-cascade-semantic-id="'+t.semantic_id+'">'+
                    '<rect x="'+(10+i*120)+'" y="10" width="100" height="70" fill="white" stroke="black"/></g>').join('')+'</svg>'});
              const view = (key,level,targets) => ({key,level,state:'unchanged',current:side(targets),proposed:side(targets)});
              const team = {...target('team'),drill_choices:[{view_key:'team-code',level:'codeViews',scope_id:'team'}]};
              PlanViewer.initPairedC4Review({owner_work_id:'epic_001',approval_context:null,views:[
                view('containers','containerViews',[{...target('service'),label:'Service',drill_choices:choices}]),
                view('overview','componentViews',[team,target('workspace')]),
                view('focused','componentViews',ambiguous?[team,target('other')]:[team]),
                view('team-code','codeViews',[target('function')]),
              ],changed_views:[],resources:[],diffs:{}}, {document,host:document.getElementById('review')});
            }'''
            page.evaluate(setup, False)
            page.locator('[data-review-tab="c4"]').click()
            for side in ('current', 'proposed'):
                page.locator('.paired-c4-view-select').select_option('containers\0containerViews')
                page.locator(f'.paired-c4-side-{side} [aria-label="element service"]').click()
                assert page.locator('.paired-c4-view-select').input_value() == 'overview\0componentViews'
                assert page.locator('.paired-c4-drill-choices').count() == 0
                page.locator('.paired-c4-side-current [aria-label="element workspace"]').wait_for()
                page.locator('.paired-c4-side-proposed [aria-label="element workspace"]').wait_for()
                page.locator('.paired-c4-up').click()
                assert page.locator('.paired-c4-view-select').input_value() == 'containers\0containerViews'
            # Returning from L4 preserves the focused L3 view used to get there.
            page.locator('.paired-c4-view-select').select_option('focused\0componentViews')
            page.locator('.paired-c4-side-proposed [aria-label="element team"]').click()
            assert page.locator('.paired-c4-view-select').input_value() == 'team-code\0codeViews'
            page.locator('.paired-c4-up').click()
            assert page.locator('.paired-c4-view-select').input_value() == 'focused\0componentViews'
            page.locator('.paired-c4-up').click()
            assert page.locator('.paired-c4-view-select').input_value() == 'containers\0containerViews'
            assert page.locator('.paired-c4-up').is_disabled()
            # Direct entry into L4 has no origin: return to the full L3 overview.
            page.evaluate(setup, False)
            page.locator('[data-review-tab="c4"]').click()
            page.locator('.paired-c4-view-select').select_option('team-code\0codeViews')
            page.locator('.paired-c4-up').click()
            assert page.locator('.paired-c4-view-select').input_value() == 'overview\0componentViews'
            assert page.locator('.paired-c4-up').is_enabled()
            page.evaluate(setup, True)
            page.locator('[data-review-tab="c4"]').click()
            page.locator('.paired-c4-side-proposed [aria-label="element service"]').click()
            page.wait_for_function('document.activeElement.classList.contains("paired-c4-drill-choice")')
            chooser = page.locator('.paired-c4-drill-choices')
            assert 'Service' in chooser.inner_text()
            rect = chooser.bounding_box()
            assert 0 <= rect['y'] < 720
            page.keyboard.press('Escape')
            assert chooser.count() == 0
            page.locator('.paired-c4-side-proposed [aria-label="element service"]').click()
            page.get_by_role('button', name='Team components', exact=True).click()
            assert page.locator('.paired-c4-view-select').input_value() == 'focused\0componentViews'
        finally:
            browser.close()


@pytest.mark.parametrize('publication_fails', [False, True])
def test_project_tab_never_displays_publication_empty_baseline(publication_fails):
    playwright = pytest.importorskip('playwright.sync_api')
    assets = Path(__file__).parents[2] / 'cascade/war_room/static'
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f'Chromium unavailable: {exc}')
        try:
            page = browser.new_page()
            page.set_content('<main><section id="review"></section></main>')
            page.add_script_tag(path=str(assets / 'plan_viewer.js'))
            page.evaluate('''() => {
              const publication = {state:'empty_baseline', owner_work_id:'epic_047',
                summary:'validated proposal is compared with an explicit empty baseline',
                reason:'validated proposal is compared with an explicit empty baseline',
                views:[], diffs:{}, approval_context:null};
              window.calls = {publication:0, project:0};
              window.review = PlanViewer.initPairedC4Review(publication, {
                document, host:document.getElementById('review'),
                refreshPayload: () => { calls.publication++;
                  return new Promise((resolve,reject) => {window.finishPublication = () => resolve({...publication});
                    window.failPublication = () => reject(new Error('Publication unavailable'));}); },
                loadDraft: () => { calls.project++;
                  return new Promise((resolve,reject) => {window.finishProject = () => resolve({
                    project_comparison:true,state:'ready',summary:'Current project compared with proposed project',
                    views:[],diffs:{},approval_context:null,
                    project_revisions:{current:'main-sha',projected:'projected-sha',current_branch:'main'}});
                    window.failProject = () => reject(new Error('Project render unavailable'));}); },
              });
              review.refresh();
            }''')
            page.wait_for_function('typeof window.finishPublication === "function"')
            page.locator('[data-review-tab="c4"]').click()
            assert 'empty baseline' not in page.locator('#review').inner_text()
            page.evaluate('failPublication()' if publication_fails else 'finishPublication()')
            page.wait_for_function('calls.project === 1')
            assert 'empty baseline' not in page.locator('#review').inner_text()
            page.evaluate('failProject()')
            page.wait_for_function('document.getElementById("review").textContent.includes("Project render unavailable")')
            assert 'empty baseline' not in page.locator('#review').inner_text()
            # Retries call the project loader directly, even when publication is broken.
            page.evaluate('void review.refresh()')
            page.wait_for_function('calls.project === 2')
            assert page.evaluate('calls.publication') == 1
            page.evaluate('finishProject()')
            page.wait_for_function('document.querySelector(".paired-c4-project-baseline")')
            assert 'Current: main' in page.locator('#review').inner_text()
            assert 'empty baseline' not in page.locator('#review').inner_text()
            page.evaluate('review.stopRefresh()')
        finally:
            browser.close()
