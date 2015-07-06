#!/usr/bin/python
#
#   Copyright 2015 Reliance Jio Infocomm, Ltd.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

import time
import datetime
import gdata.gauth
import gdata.spreadsheets.client
from gdata.spreadsheets.data import ListEntry
from launchpadlib.launchpad import Launchpad

def format_date_for_gdata(ts):
    if ts is None:
        return ts 
    return '%d/%d/%d %d:%02d:%02d' % (ts.month,
                                      ts.day,
                                      ts.year,
                                      ts.hour,
                                      ts.minute,
                                      ts.second)


class BugSync(object):
    tokenfile = 'mytoken'

    client_id = '91766RFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEapps.googleusercontent.com'
    client_secret = 'FAKEFAKEFAKEFAKEFAKEFAKE'
    all_lp_statuses = "New, Incomplete, Opinion, Invalid, Won't Fix, Expired, Confirmed, Triaged, In Progress, Fix Committed, Fix Released, Incomplete (with response), Incomplete (without response)".split(', ')

    def __init__(self, spreadsheet_key='16MGxXutr9N38MPq8T2ObX8QCXVoR2LMb9KQs1qIvHrI'):
        self.spreadsheet_key = spreadsheet_key
        self._spr_client = None
        self._lp_conn = None
        self._people_cache = {}

    def get_assignee_name(self, task):
        if not task.assignee_link:
            return 'None'
        if task.assignee_link not in self._people_cache:
            self._people_cache[task.assignee_link] = task.assignee.display_name
        return self._people_cache[task.assignee_link]


    @property
    def lp_conn(self):
        if not self._lp_conn:
            self._lp_conn = Launchpad.login_with('lp-shell', 'production', version='devel')
        return self._lp_conn
    
    @property
    def spr_client(self):
        if True or not self._spr_client:
            try:
                with open(self.tokenfile, 'r') as fp:
                    blob = fp.read()
                token = gdata.gauth.token_from_blob(blob)
                token = gdata.gauth.OAuth2Token(client_id=self.client_id,
                                                client_secret=self.client_secret,
                                                scope = 'https://spreadsheets.google.com/feeds',
                                                user_agent='Jio Bugs',
                                                refresh_token=token.refresh_token)
            except:
                token = gdata.gauth.OAuth2Token(client_id=self.client_id,
                                                client_secret=self.client_secret,
                                                scope = 'https://spreadsheets.google.com/feeds',
                                                user_agent='Jio Bugs')

                print 'Visit the following URL in your browser to authorise this app:'
                print str(token.generate_authorize_url(redirect_url='urn:ietf:wg:oauth:2.0:oob'))
                print 'After agreeing to authorise the app, copy the verification code from the browser.'
                access_code = raw_input('Please enter the verification code: ')

                token.get_access_token(access_code)

                f = open(self.tokenfile, 'w')
                blob = gdata.gauth.token_to_blob(token)
                f.write(blob)
                f.close()

            spr_client = gdata.spreadsheets.client.SpreadsheetsClient(source='Jio Bugs')
            self._spr_client = token.authorize(spr_client)
        return self._spr_client

    def update_sheet(self, lpdata):
        feed, sheet_key = self.get_feed_for_worksheet('Raw data')
        seen_bugs = set()
        for row in feed.entry:
            d = row.to_dict()
            bug_id = d['id']

            seen_bugs.add(bug_id)
            if bug_id in lpdata and lpdata[bug_id] != d:
                print 'difference!'
                print 'row.to_dict: %r' % (d,)
                print 'lpdata[bug_id]: %r' % (lpdata[bug_id],)
                for key in lpdata[bug_id]:
                    row.set_value(key, lpdata[bug_id][key])
                self.spr_client.update(row)
        missing_bugs = set(lpdata.keys()) - seen_bugs
        for bug_id in missing_bugs:
            print 'Adding new bug: %s' % (bug_id,)
            row = ListEntry()
            for key in lpdata[bug_id]:
                row.set_value(key, lpdata[bug_id][key])
            self.spr_client.add_list_entry(row, self.spreadsheet_key, sheet_key)

    def get_feed_for_worksheet(self, name):
        for sheet in self.spr_client.get_worksheets(self.spreadsheet_key).entry:
            if sheet.title.text == name:
                sheet_key = sheet.id.text.split('/')[-1]
                return self.spr_client.get_list_feed(self.spreadsheet_key, sheet_key), sheet_key
            
    def add_timestamped_entry(self, worksheet_name):
        feed, worksheet_key = self.get_feed_for_worksheet(worksheet_name)
        main_entry = feed.entry[0]
        new_entry = ListEntry()
        new_entry.from_dict(main_entry.to_dict())
        new_entry.set_value('timestamp', format_date_for_gdata(datetime.datetime.utcnow()))
        self.spr_client.add_list_entry(new_entry, self.spreadsheet_key, worksheet_key)

    def sync_recent_bug_data_from_lp(self):
        jio = self.lp_conn.projects['jio']
        tasks = jio.searchTasks(status=self.all_lp_statuses, modified_since=datetime.datetime.now()-datetime.timedelta(days=2))
        data = {}
        for task in tasks:
            print task.title
            bug = task.bug
            data[str(bug.id)] = {'id': str(bug.id),
                                 'title': bug.title,
                                 'assignee': self.get_assignee_name(task),
                                 'importance': task.importance,
                                 'datecreated': format_date_for_gdata(task.date_created),
                                 'lastupdated': format_date_for_gdata(bug.date_last_updated),
                                 'dateclosed': format_date_for_gdata(task.date_closed),
                                 'dateleftnew': format_date_for_gdata(task.date_left_new),
                                 'tags': bug.tags and ' '.join(bug.tags) or None,
                                 'status': task.status,
                                }

        self.update_sheet(data)

        
if __name__ == '__main__':
    bs = BugSync()
    bs.sync_recent_bug_data_from_lp()
#    bs.add_timestamped_entry('operational-issues-counts')
