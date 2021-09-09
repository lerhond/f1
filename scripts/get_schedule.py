#!/usr/bin/env python3

import json
import pytz
import re
import requests
import time

from bs4 import BeautifulSoup
from collections import defaultdict
from datetime import datetime, timedelta
from geopy import geocoders
from timezonefinder import TimezoneFinder


SESSIONS = [
    (('Formula 1', 'First Practice'), ('f1', 'fp1')),
    (('Formula 1', 'Practice 1'), ('f1', 'fp1')),
    (('Formula 1', 'Second Practice'), ('f1', 'fp2')),
    (('Formula 1', 'Practice 2'), ('f1', 'fp2')),
    (('Formula 1', 'Third Practice'), ('f1', 'fp3')),
    (('Formula 1', 'Practice 3'), ('f1', 'fp3')),
    (('Formula 1', 'Sprint'), ('f1', 'sprintQualifying')),
    (('Formula 1', 'Qualifying'), ('f1', 'qualifying')),
    (('Formula 1', 'Grand Prix'), ('f1', 'gp')),

    (('Formula 2', 'Practice'), ('f2', 'practice')),
    (('Formula 2', 'Qualifying'), ('f2', 'qualifying')),
    (('Formula 2', 'First Race'), ('f2', 'sprint1')),
    (('Formula 2', 'Second Race'), ('f2', 'sprint2')),
    (('Formula 2', 'Third Race'), ('f2', 'feature')),

    (('Formula 3', 'Practice'), ('f3', 'practice')),
    (('Formula 3', 'Qualifying'), ('f3', 'qualifying')),
    (('Formula 3', 'First Race'), ('f3', 'race1')),
    (('Formula 3', 'Second Race'), ('f3', 'race2')),
    (('Formula 3', 'Third Race'), ('f3', 'race3')),

    (('W Series', 'Practice'), ('wseries', 'practice1')),
    (('W Series', 'Qualifying'), ('wseries', 'qualifying')),
    (('W Series', 'Race'), ('wseries', 'race')),
]

EXCLUDED_SESSIONS = [
    ('Formula 1', 'Sprint Victory'),
    ('Formula 2', 'Qualifying Session (Group B)'),
]


def get_page(url, soup=False):
    content = requests.get(url).content.decode('utf-8').replace('\xa0', ' ')
    time.sleep(2)
    return BeautifulSoup(content, 'html.parser') if soup else content


def main():
    geocoder = geocoders.Nominatim(user_agent='F1 calendar scraping script')
    tzf = TimezoneFinder()
    year = datetime.now().year

    schedule_page = get_page(f'https://www.formula1.com/en/racing/{year}.html', soup=True)
    gps = schedule_page.find_all('a', {'class': 'event-item-wrapper event-item-link'})

    db = {}
    not_found_in_db = []

    for _, (series, _) in SESSIONS:
        if series not in db:
            with open(f'../_db/{series}/{year}.json', 'r') as f:
                db[series] = json.load(f)

    out_file = open('schedule.txt', 'w')

    for gp in gps:
        href = gp.attrs['href']
        name = href.split('/')[-1].split('.')[0]
        if 'Pre-Season-Test' in name:
            continue

        out_file.write(name + '\n\n')
        print(name)
        print()

        gp_page = get_page('https://www.formula1.com' + href)
        city = None
        for line in gp_page.split('\n'):
            if '"address"' in line:
                city = json.loads('{' + line + '}')['address']
                break
        if city is None:
            continue

        geocode = geocoder.geocode(city)
        timezone = pytz.timezone(
            tzf.timezone_at(
                lat=geocode.point.latitude,
                lng=geocode.point.longitude))
        print(city, geocode, (geocode.point.latitude, geocode.point.longitude), timezone, sep='\n')
        print()

        schedules = defaultdict(lambda: {})
        date = None
        saturday = None
        db_race_by_series = {}

        timetable_page = get_page(
            f'https://www.formula1.com/en/racing/{year}/{name}/Timetable.html',
            soup=True)

        for row in timetable_page.find_all('tr'):
            cells = [cell.text.strip() for cell in row.find_all('td')]

            if len(cells[0]) > 0 and len(cells[1]) == 0 and len(cells[2]) == 0:
                day = re.sub(r'\D', '', cells[0].split(' ')[1])
                month = cells[0].split(' ')[2]
                date = timezone.localize(datetime.strptime(f'{day} {month} 2021', '%d %B %Y'))
                print()
                print(cells[0], date, sep='\n')
                print()
            elif date is not None:
                if saturday is None:
                    saturday = date + timedelta(days=5 - date.weekday())
                    for series in db:
                        for race in db[series]['races']:
                            for start_time_str in race['sessions'].values():
                                start_time_str = start_time_str.replace('Z', '')
                                start_time = datetime.fromisoformat(start_time_str)
                                if start_time.date() == saturday.date():
                                    db_race_by_series[series] = race

                excluded = False
                for session in EXCLUDED_SESSIONS:
                    if session[0] in cells[0] and session[1] in cells[1]:
                        excluded = True
                        break
                if excluded:
                    continue

                for session, keys in SESSIONS:
                    if session[0] in cells[0] and session[1] in cells[1]:
                        hour, minute = cells[2].split('-')[0].strip().split(':')
                        start_time = date.replace(hour=int(hour), minute=int(minute))
                        start_time_iso = start_time.astimezone(
                            pytz.utc).isoformat().replace('+00:00', 'Z')
                        schedules[keys[0]][keys[1]] = start_time_iso
                        print(cells, keys, start_time, start_time_iso, sep='\n')

        for series, schedule in sorted(schedules.items()):
            if series in db_race_by_series:
                db_race_by_series[series]['sessions'] = schedule
                if 'tbc' in db_race_by_series[series]:
                    del db_race_by_series[series]['tbc']
            else:
                not_found_in_db.append((series, name, saturday.date()))

            as_json = json.dumps(schedule, indent='\t' * 4)
            out_file.write(series + '\n')
            out_file.write(as_json + '\n')
            print(series)
            print(as_json)

        out_file.write('\n\n')
        out_file.flush()
        print()
        print()

    out_file.close()

    if not_found_in_db:
        print('WARNING: Couldn\'t find weekend in DB:')
        for item in not_found_in_db:
            print(item)

    for series in db:
        with open(f'../_db/{series}/{year}.json', 'w') as f:
            f.write(json.dumps(db[series], indent='\t') + '\n')


if __name__ == '__main__':
    main()
