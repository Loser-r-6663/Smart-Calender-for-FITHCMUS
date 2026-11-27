"""Run the existing NiceGUI client with a fixed fictional Search dataset."""

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from nicegui import ui

from client.config import AppConfig
from client.core.mock_backend import MockBackend
from client.pages.calendar import register_calendar_page
from client.pages.login import register_login_page
from client.pages.settings import register_settings_page
from client.pages.signup import register_signup_page


def main():
    config=AppConfig(mode='mock',host='127.0.0.1',port=int(os.getenv('CLIENT_PORT','8091')),
                     storage_secret='fictional-search-demo-only')
    rows=json.loads(Path(__file__).with_name('tasks.json').read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='search-demo-') as directory:
        for row in rows:
            scope='personal' if row.get('user_id') else 'public'
            row['source_url']=f'http://127.0.0.1:{config.port}/demo-source/{scope}/{row["id"]}'
        fixture=Path(directory)/'tasks.json'
        fixture.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
        backend=MockBackend(fixture)
        ui.add_css(Path('client/static/styles.css'),shared=True)
        register_login_page(backend,config)
        register_signup_page(backend,config)
        register_calendar_page(backend,config)
        register_settings_page(backend,config)

        @ui.page('/demo-source/{scope}/{task_id}')
        def source(scope:str,task_id:str):
            row=next((row for row in rows if row['id']==task_id and
                      ('personal' if row.get('user_id') else 'public')==scope),None)
            ui.label('Nguồn giả lập — không phải dữ liệu thật').classes('text-h6')
            ui.label(row['title'] if row else 'Không có bản ghi này trong fixture')

        ui.run(host=config.host,port=config.port,storage_secret=config.storage_secret,
               title='Search demo — dữ liệu giả lập',show=False,reload=False)


if __name__ in {'__main__','__mp_main__'}:
    main()
