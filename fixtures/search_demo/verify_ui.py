"""Verify the fictional launcher with the installed local model and real browser."""

import json, os, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from test_search_ui import submit, close_details, assert_keys


def main():
    if not os.environ.get("SEARCH_SEMANTIC_MODEL"):
        raise RuntimeError("Set SEARCH_SEMANTIC_MODEL to the installed pinned local model")
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    directory=Path(tempfile.mkdtemp(prefix='commit7-demo-app-'))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    env={**os.environ,'CLIENT_PORT':str(port),'PYTHON_DOTENV_DISABLED':'1'}
    log=(directory/'app.log').open('w',encoding='utf8')
    process=subprocess.Popen([sys.executable,'-B','-X','utf8','-m','fixtures.search_demo.app'],env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    results=[]
    try:
        for _ in range(150):
            if process.poll() is not None: raise RuntimeError('Fictional launcher failed; inspect local app.log')
            try:
                with urlopen(base+'/login',timeout=1):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Fictional launcher unavailable')
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='msedge',headless=True)
            version=browser.version
            for width,height in [(1280,900),(390,844)]:
                context=browser.new_context(viewport={'width':width,'height':height})
                context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base) else route.abort())
                page=context.new_page();page.set_default_timeout(120000)
                page.goto(base+'/login')
                page.get_by_label('Username',exact=True).fill('student')
                page.get_by_label('Password',exact=True).fill('demo')
                page.get_by_role('button',name='Sign in',exact=True).click()
                page.get_by_role('button',name='Search tasks',exact=True).wait_for()
                page.wait_for_function('window.did_handshake === true')
                expect(page.locator('.task-search-popover')).not_to_be_visible()
                page.screenshot(path=str(directory/f'closed-{width}.png'),full_page=True,animations='disabled')
                exact='Thời điểm hoàn tất nghĩa vụ tài chính'
                submit(page,exact)
                key='public:11111111-1111-4111-8111-111111111111'
                assert_keys(page,[key])
                page.locator('.search-result').click()
                expect(page.locator('.search-detail-dialog .detail-title')).to_have_text(exact)
                with context.expect_page() as popup:
                    page.locator('.search-detail-dialog .source-link').click()
                expected=base+'/demo-source/public/'+key.split(':')[1]
                expect(popup.value.get_by_text('Nguồn giả lập — không phải dữ liệu thật',exact=True)).to_be_visible()
                assert popup.value.url==expected
                popup.value.close();close_details(page)
                points=[]
                for query,keys in [
                    ('5 điểm',['personal:88888888-8888-4888-8888-888888888888']),
                    ('từ 5 điểm',['personal:88888888-8888-4888-8888-888888888888','public:66666666-6666-4666-8666-666666666666']),
                    ('nhiều hơn 5 điểm',['public:66666666-6666-4666-8666-666666666666'])]:
                    submit(page,query);assert_keys(page,keys);points.append(dict(query=query,ordered_keys=keys))
                submit(page,'hạn cuối đóng học phí')
                expect(page.locator(f'[data-search-key="{key}"]')).to_be_visible(timeout=120000)
                expect(page.get_by_text('Searching…',exact=True)).not_to_be_visible(timeout=120000)
                expect(page.locator('.search-count')).to_be_visible(timeout=120000)
                keys=page.locator('.search-result').evaluate_all('xs=>xs.map(x=>x.dataset.searchKey)')
                assert keys[0]==key,keys
                page.screenshot(path=str(directory/f'paraphrase-{width}.png'),full_page=True,animations='disabled')
                page.locator(f'[data-search-key="{key}"]').click()
                expect(page.locator('.search-detail-dialog .detail-title')).to_have_text(exact)
                page.screenshot(path=str(directory/f'details-{width}.png'),full_page=True,animations='disabled')
                close_details(page)
                page.get_by_role('button',name='Clear',exact=True).click()
                expect(page.locator('.search-result')).to_have_count(0)
                expect(page.locator('.search-count')).to_have_count(0)
                results.append(dict(viewport=[width,height],mock_login=True,exact_key=key,source_destination='local controlled /demo-source/public/'+key.split(':')[1],point_queries=points,paraphrase_query='hạn cuối đóng học phí',paraphrase_ordered_keys=keys,expected_position=keys.index(key)+1,clear_idle=True))
                context.close()
            browser.close()
    finally:
        process.terminate();process.wait(timeout=15);log.close()
    from academic_search import map_task,search_records
    from DataProcessor.Standardization.ExtractedTask import ExtractedTask
    rows=json.loads(Path('fixtures/search_demo/tasks.json').read_text(encoding='utf8'))
    records=[map_task(ExtractedTask.model_validate(row),scope='personal' if row.get('user_id') else 'public') for row in rows]
    assert search_records(records,'hạn cuối đóng học phí').hits==()
    report=dict(tested_revision=revision,mode='fictional mock launcher / actual local model',corpus_records=len(rows),browser=version,model_revision='fd1525a9fd15316a2d503bf26ab031a61d056e98',cutoff=.86,keyword_paraphrase_keys=[],screenshots=str(directory),runs=results)
    Path('fixtures/search_demo/ui_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print('Verified launcher login, source destination, point cases, real-model rank 1, and Clear at both widths')
    print('Screenshots:',directory)


if __name__ == "__main__":
    main()
