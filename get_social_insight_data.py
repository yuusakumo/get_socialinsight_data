#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import getpass

import os

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.safari.service import Service as SafariService

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import sys
import time

WAIT_TIME_OF_VIEW = 3


def parse_args():
    '''
    set and parse the arguments of the programs
    '''

    parser = argparse.ArgumentParser(
        description='get the time series of the keyword from Google Trends.')

    parser.add_argument('keyword',
                        type=str,
                        help='specify the keyword to search for')

    parser.add_argument('start_date',
                        type=str,
                        help='specify the start date (Format: YYYY-MM-DD)')

    parser.add_argument('end_date',
                        type=str,
                        help='specify the end date (Format: YYYY-MM-DD)')

    parser.add_argument(
        "-s",
        "--save",
        type=str,
        default="",
        help=
        'specify the save directory of downloaded csv files (Default: SI_keyword/csv)'
    )

    args = parser.parse_args()

    return args


class SocialInsightData():
    '''
    Social Insight から取得したデータを管理するクラス

    Attributes
    -----------
    _keyword (str) : 検索キーワード
    _keyword_id (str) : 検索キーワードの ID
    _start_date (str) : データ取得の開始日 (Format: YYYY-MM-DD)
    _end_date (str) :データ取得の終了日 (Format: YYYY-MM-DD)
    
    _save_dir : 取得したデータ(csv)を保存するディレクトリ
    
    _data (dict[int, dict]) : 各 period の検索スコアの時系列データ
        NOTE: スケーリングとかしないので基本的には 1 つの period になる
    _num_period (int) : period の個数
    _max_period (int) : 長さが最大の period (1オリジン)
    '''
    def __init__(self):

        self._keyword = ""
        self._keyword_id = ""

        self._start_date = ""
        self._end_date = ""

        self._save_dir = ""

        self._data = dict()

        self._num_period = 0
        self._max_period = 0

    def shift_date(self, date: str, shift: int):
        '''
        基準日から shift だけずらした日付を得る

        Parameters
        -----------
        date (str): 基準日 (Format: YYYY-MM-DD)
        shift (int): shift する日数 (shift >= 0)

        Returns
        -----------
        str : shift だけずらした日付の文字列 (Format: YYYY-MM-DD)
        '''
        assert shift >= 0

        dt = datetime.strptime(date, '%Y-%m-%d')
        shifted_dt = dt + timedelta(days=shift)  # shift だけずらした日付を得る
        shifted_date = shifted_dt.strftime('%Y-%m-%d')

        return shifted_date

    def make_save_dir(self):
        '''
        取得したデータを保存するディレクトリの作成
        '''
        assert self._save_dir != ""

        print(f"NOTICE: save directory is {self._save_dir}")

        if not os.path.exists(self._save_dir):
            os.makedirs(self._save_dir)

    def get_Social_Insight_data(self,
                                start_date: str,
                                end_date: str,
                                keyword: str,
                                save_dir: str = ""):
        '''
        start_date から end_date までの検索キーワード keyword の時系列データを取得

        Parameters
        -----------
        start_date (str) : データ取得の開始日 (Format: YYYY-MM-DD)
        end_date (str) : データ取得の終了日 (Format: YYYY-MM-DD)
        keyword (str) : 検索ワード
        
        save_dir (str) : ダウンロードした csv ファイルの保存ディレクトリ (Default: "")
             ※ "" であるときは，SI_keyword/csv に保存
        '''

        self._start_date = start_date
        self._end_date = end_date
        self._keyword = keyword

        if save_dir != "":
            self._save_dir = save_dir
        else:
            self._save_dir = f"SI_{self._keyword}/csv"

        self.make_save_dir()

        self._num_period = 0  # 重複したデータの区間数
        self._max_period = 0  # 最大長の period 番号

        # start_date から end_date までの区間を分割してデータを取得
        web_driver = self.open_web_driver('chrome')
        self.login_Social_Insight(web_driver)

        self._keyword_id = self.get_keyword_id(web_driver)

        date = self._start_date
        while date < self._end_date:
            if os.path.exists(self.save_csv_file(date)):
                print(
                    f"NOTICE: the data {self.save_csv_file(date)} already exists",
                    file=sys.stderr)
            else:
                self.get_Social_Insight_data_at_date(date,
                                                     web_driver)  # 1 日分のデータを取得
            self.add_data_from_csv(date)  # ダウンロードしたデータを _data に追加
            date = self.shift_date(date, 1)

    def auth_Social_Insight(self) -> (str, str):

        # input KG id
        SI_id_file = '.si_id'
        if os.path.exists(SI_id_file):
            with open(SI_id_file, 'r') as f:
                auth_id = f.readline()
        else:
            print('Please input Social Insight id (e.g., example@email.com)',
                  file=sys.stderr)
            print("id: ", end="", file=sys.stderr)
            auth_id = input()
            with open(SI_id_file, 'w') as f:
                f.write(auth_id)

        # input KG pass
        SI_pass_file = '.si_pass'
        if os.path.exists(SI_pass_file):
            with open(SI_pass_file, 'r') as f:
                auth_pass = f.readline()
        else:
            print('Please input Socal Insight password', file=sys.stderr)
            print("password: ", end="", file=sys.stderr)
            auth_pass = getpass.getpass()
            with open(SI_pass_file, 'w') as f:
                f.write(auth_pass)

        return (auth_id, auth_pass)

    def login_Social_Insight(self, web_driver):

        auth_id, auth_pass = self.auth_Social_Insight()

        web_driver.get("https://auth.userlocal.jp/login?")
        print(auth_id, auth_pass)
        web_driver.find_element(By.NAME, "email").send_keys(auth_id)
        web_driver.find_element(By.NAME, "password").send_keys(auth_pass)
        WebDriverWait(web_driver, 10).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//input[@value='ログイン']"))).click()

        time.sleep(WAIT_TIME_OF_VIEW)

    def add_data_from_csv(self, date: str):

        if not self._data:
            self._data[0] = dict()
            self._num_period = 1

        # ダウンロードした csv ファイルの読み込みと，_data への格納
        with open(self.save_csv_file(date), "r") as f:
            for line in f.readlines():
                sline = line.strip()
                # ASSERTION: 時系列データの先頭は "20" であること
                if sline[0:2] != "20":
                    continue
                t, data = sline.split(",")  # t の書式: YYYY-MM-DDTHH

                self._data[0][t] = data

    def get_Social_Insight_data_at_date(self, date: str, web_driver):
        '''
        日付 date の X の投稿数データを取得

        Parameters
        -----------
        date (str) : 基準日 (Format: YYYY-MM-DD)
        '''

        # assert self._web_driver is not None
        assert self._save_dir != ""

        print(f"NOTICE: download Social Insight data at {date}",
              f"with keyword {self._keyword}",
              file=sys.stderr)

        print(f"NOTICE: url is {self.social_insight_url(date)}",
              file=sys.stderr)

        # データの取得
        web_driver.get(self.social_insight_url(date))
        time.sleep(WAIT_TIME_OF_VIEW)

        for i in range(
                web_driver.execute_script("return Highcharts.charts.length;")):

            csv = web_driver.execute_script(
                f"return Highcharts.charts[{i}]?.getCSV?.();")
            if not csv:
                continue

            if "時間帯別" in csv:
                csv_list = csv.splitlines()[1:]
                with open(self.save_csv_file(date), 'w') as f:
                    for line in csv_list:
                        tok = line.split(',')
                        print(line, end="")
                        t = int(tok[0])
                        data = tok[1]
                        f.write(f"{date}T{t:02},{data}\n")
                print(
                    f"NOTICE: success donwnload csv file {self.save_csv_file(date)}",
                    f"at {datetime.now()}",
                    file=sys.stderr)

                return

        else:
            print(f"ERROR: does not download csv file at {datetime.now()}",
                  file=sys.stderr)

    def get_keyword_id(self, web_driver):

        web_driver.get("https://social-admin.userlocal.jp/keywords")
        WebDriverWait(web_driver, 10).until(
            EC.presence_of_all_elements_located((By.TAG_NAME, "a")))
        links = web_driver.find_elements(By.TAG_NAME, "a")
        for link in links:
            if link.text.strip() == self._keyword:
                href = link.get_attribute("href")
                if "/keywords/" in href:
                    keyword_id = href.split("/keywords/")[1].split("/")[0]
                    time.sleep(WAIT_TIME_OF_VIEW)

                    return keyword_id
        else:
            print(
                f"ERROR: does not find keyword id of {self._keyword} at {datetime.now()}",
                file=sys.stderr)

    def social_insight_url(self, date: str):
        assert self._keyword_id != ""

        url = f"https://social-admin.userlocal.jp/keywords/{self._keyword_id}/tw/summary?end_date={date}&start_date={date}"

        return url

    def save_csv_file(self, date: str):
        save_file = f"{self._save_dir}/data_{date}.csv"

        return save_file

    def open_web_driver(self, kind_driver: str = "chrome"):
        '''
        データ取得の初期化
        '''
        assert kind_driver in {"chrome", "safari"}

        if kind_driver == "chrome":
            # ChromeDriverのパスを指定してサービスを作成(Selenium 4 系以降で推奨)
            service = Service("driver/chromedriver")
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')  # ウィンドウを開かないようにする

            web_driver = webdriver.Chrome(service=service, options=options)
        elif kind_driver == "safari":
            service = SafariService()
            options = webdriver.SafariOptions()
            # 例：テクニカルプレビュー版の Safari を使用したいとき
            # options.use_technology_preview = True

            web_driver = webdriver.Safari(service=service, options=options)

        return web_driver

    def close_web_driver(self, web_driver):

        assert web_driver is not None
        web_driver.quit()

    def print_data(self):

        for p, data_dict in sorted(self._data.items(), key=lambda x: x[0]):
            for t, data in sorted(data_dict.items(), key=lambda x: x[0]):
                print(f"ALL_DATA: period {p} t {t} data {data}")

    def print_data_of_max_period(self):

        p = self._max_period
        for t, data in sorted(self._data[p].items(), key=lambda x: x[0]):
            print(f"DATA: period {p} t {t} data {data}")


if __name__ == '__main__':

    args = parse_args()

    keyword = args.keyword  # 検索キーワード
    start_date = args.start_date  # データ取得期間の開始日
    end_date = args.end_date  # データ取得期間の終了日
    save_dir = args.save  # ダウンロードした csv ファイルの保存ディレクトリ

    getter = SocialInsightData()
    getter.get_Social_Insight_data(start_date, end_date, keyword, save_dir)
    getter.print_data()  # 全ての period のデータを出力
    getter.print_data_of_max_period()  # 最大の period のデータを出力
