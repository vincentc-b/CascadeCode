"""Module selection and changed-block navigation in rendered design comparisons."""
from pathlib import Path

import pytest

from cascade.war_room.plan_comparison import compare_document


def test_design_tree_and_change_navigation():
    playwright = pytest.importorskip('playwright.sync_api')
    assets = Path(__file__).parents[2] / 'cascade/war_room/static'
    context = '\n\n'.join('Unchanged paragraph ' + str(i) for i in range(60))
    before = '# Module\n\nOld first.\n\n' + context + '\n\nOld last.\n'
    after = before.replace('Old first.', 'New first.').replace('Old last.', 'New last.')
    designs = [
        {**compare_document('pkg/core/DESIGN.md', before, after), 'state': 'changed'},
        {**compare_document('pkg/new/DESIGN.md', '', '# New module\n'), 'state': 'added'},
        {**compare_document('old/DESIGN.md', '# Retired\n', ''), 'state': 'removed'},
    ]
    comparison = {
        'state': 'draft', 'message': 'Committed branch preview',
        'current_revision': 'base', 'proposed_revision': 'head', 'designs': designs,
        'design_tree': [{'path': d['path'], 'state': d['state']} for d in designs]
        + [{'path': 'pkg/stable/DESIGN.md', 'state': 'unchanged'}],
    }
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={'width': 1400, 'height': 900})
            page.set_content('<section id="review"></section>')
            page.add_style_tag(path=str(assets / 'plan_viewer.css'))
            page.add_script_tag(path=str(assets / 'vendor/marked.min.js'))
            page.add_script_tag(path=str(assets / 'plan_viewer.js'))
            page.evaluate('''comparison => PlanViewer.initPairedC4Review(
                {state: 'ready', views: [], resources: []},
                {document, host: document.getElementById('review'), comparison})''', comparison)
            page.locator('[data-review-tab="design"]').click()
            assert page.locator('.review-design-tree button').count() == 3
            assert page.locator('span[data-design-state="unchanged"]', has_text='stable').count() == 1
            assert page.locator('.review-design-changes h3').inner_text() == 'pkg/core/DESIGN.md'
            proposed = page.locator('.review-rendered-after')
            proposed.get_by_role('button', name='Next change', exact=True).click()
            assert proposed.locator('.review-change-active').inner_text() == 'New first.'
            proposed.get_by_role('button', name='Next change', exact=True).click()
            assert proposed.locator('.review-change-active').inner_text() == 'New last.'
            assert proposed.locator('[aria-live="polite"]').inner_text() == 'Change 2 of 2'
            assert page.evaluate('window.scrollY') > 0
            proposed.get_by_role('button', name='Next change', exact=True).click()
            assert proposed.locator('.review-change-active').inner_text() == 'New first.'
            proposed.get_by_role('button', name='Previous change', exact=True).click()
            assert proposed.locator('.review-change-active').inner_text() == 'New last.'
            page.locator('[data-design-path="old/DESIGN.md"]').click()
            assert page.locator('.review-design-changes h3').inner_text() == 'old/DESIGN.md'
            assert page.locator('.review-rendered-after').inner_text().endswith('Removed in proposed revision.')
            page.locator('.review-rendered-before').get_by_role('button', name='Next change', exact=True).click()
            assert page.locator('.review-change-active').inner_text() == 'Retired'
            page.locator('[data-design-path="pkg/new/DESIGN.md"]').click()
            assert page.locator('.review-rendered-before').inner_text().endswith('Not present in current revision.')
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        finally:
            browser.close()
