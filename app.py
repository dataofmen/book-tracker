#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import requests
import json
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
import os
import csv
import io
from urllib.parse import quote
import threading
import uuid
import time

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# 파일 업로드 크기 제한 (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# JSON 요청 크기 제한
app.config['MAX_CONTENT_PATH'] = 5 * 1024 * 1024

# 네이버 API 설정 (환경변수 또는 직접 설정)
NAVER_CLIENT_ID = os.getenv('NAVER_CLIENT_ID', 'IvsMX1RyTuWZiGR6Reot')  # 네이버 개발자센터에서 발급
NAVER_CLIENT_SECRET = os.getenv('NAVER_CLIENT_SECRET', '4CqizzHQ2J')  # 네이버 개발자센터에서 발급

class BookTracker:
    def __init__(self, db_path='books.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                authors TEXT,
                publisher TEXT,
                published_date TEXT,
                isbn TEXT,
                description TEXT,
                thumbnail_url TEXT,
                purchase_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                price REAL,
                notes TEXT,
                kyobo_link TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 백그라운드 업데이트 작업 큐 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS update_jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                total_books INTEGER NOT NULL,
                processed_books INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME NULL
            )
        ''')
        
        # 업데이트 로그 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS update_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                book_id INTEGER NOT NULL,
                book_title TEXT NOT NULL,
                success BOOLEAN NOT NULL,
                message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES update_jobs (job_id),
                FOREIGN KEY (book_id) REFERENCES books (id)
            )
        ''')
        
        # 기존 테이블에 kyobo_link 컬럼 추가 (이미 있으면 무시됨)
        try:
            cursor.execute('ALTER TABLE books ADD COLUMN kyobo_link TEXT')
        except sqlite3.OperationalError:
            # 컬럼이 이미 존재하면 무시
            pass
        
        conn.commit()
        conn.close()
    
    def detect_language(self, text):
        """언어 감지: 한국어면 True, 영어면 False 반환"""
        # 한글 문자가 포함되어 있으면 한국어로 판단
        korean_pattern = re.compile(r'[ㄱ-ㅎㅏ-ㅣ가-힣]')
        return bool(korean_pattern.search(text))
    
    def search_book_info(self, query):
        """언어별 API 선택하여 도서 정보 검색 - 단순화된 ISBN 지원"""
        
        # ISBN 번호인지 확인 (개별 검색에서만 지원)
        if self._is_isbn(query):
            print(f"개별 ISBN 검색: {query}")
            try:
                books = self.search_by_isbn(query)
                if books:
                    return books
                else:
                    print(f"ISBN 검색 실패, 일반 검색으로 대체")
            except Exception as e:
                print(f"ISBN 검색 오류: {e}, 일반 검색으로 대체")
        
        # 일반 제목 검색
        # 검색용 제목 전처리
        clean_query = self._preprocess_title_for_search(query)
        is_korean = self.detect_language(clean_query)
        
        print(f"원본 제목: '{query}' -> 검색용: '{clean_query}'")
        
        if is_korean:
            # 한국어 제목: 네이버 Books API 사용
            books = self.search_naver_books(clean_query)
            if books:
                # 결과 필터링 및 검증
                books = self._filter_search_results(books, query)
            
            if not books:
                # 네이버에서 적합한 결과가 없으면 Google Books API도 시도
                books = self.search_google_books(clean_query)
                if books:
                    books = self._filter_search_results(books, query)
        else:
            # 영어 제목: Google Books API 사용
            books = self.search_google_books(clean_query)
            if books:
                books = self._filter_search_results(books, query)
                
            if not books:
                # Google에서 적합한 결과가 없으면 네이버 API도 시도
                books = self.search_naver_books(clean_query)
                if books:
                    books = self._filter_search_results(books, query)
        
        return books
    
    def _is_isbn(self, query):
        """ISBN 번호인지 확인"""
        # 공백, 하이픈 제거 후 숫자만 남김
        clean_query = re.sub(r'[\s-]', '', query.strip())
        
        # 10자리 또는 13자리 숫자인지 확인
        if re.match(r'^\d{10}$|^\d{13}$', clean_query):
            return True
        
        # ISBN-10: 9자리 숫자 + X
        if re.match(r'^\d{9}[0-9X]$', clean_query.upper()):
            return True
            
        return False
    
    def search_by_isbn(self, isbn):
        """ISBN으로 책 검색 - 한국 도서 특화"""
        isbn = re.sub(r'[\s-]', '', isbn.strip())  # 공백, 하이픈 제거
        print(f"  정규화된 ISBN: {isbn}")
        
        # 한국 도서인지 확인 (979-11로 시작하는 신 한국 ISBN)
        is_korean_book = isbn.startswith('979') or isbn.startswith('978') and len(isbn) >= 5 and isbn[3:5] in ['89', '11']
        
        if is_korean_book:
            print(f"  한국 도서로 판단, 네이버 우선 검색")
            # 한국 도서면 네이버 먼저
            books = self._search_naver_books_by_isbn(isbn)
            if books:
                print(f"  네이버 Books ISBN 검색 성공: {len(books)}권")
                return books
            
            # 네이버 실패시 Google Books 시도
            books = self._search_google_books_by_isbn(isbn)
            if books:
                print(f"  Google Books ISBN 검색 성공: {len(books)}권")
                return books
        else:
            print(f"  해외 도서로 판단, Google Books 우선 검색")
            # 해외 도서면 Google Books 먼저
            books = self._search_google_books_by_isbn(isbn)
            if books:
                print(f"  Google Books ISBN 검색 성공: {len(books)}권")
                return books
            
            # Google 실패시 네이버 시도
            books = self._search_naver_books_by_isbn(isbn)
            if books:
                print(f"  네이버 Books ISBN 검색 성공: {len(books)}권")
                return books
            
        print(f"  모든 ISBN 전용 검색 실패: {isbn}")
        return []
    
    def _search_google_books_by_isbn(self, isbn):
        """Google Books API로 ISBN 검색 - 개선된 검색"""
        books = []
        
        # 여러 검색 방법 시도
        search_queries = [
            f"isbn:{isbn}",  # 정확한 ISBN 검색
            f"isbn={isbn}",  # 다른 ISBN 형식
            isbn             # 일반 텍스트 검색
        ]
        
        for query in search_queries:
            try:
                print(f"  Google Books 검색 시도: {query}")
                url = f"https://www.googleapis.com/books/v1/volumes?q={quote(query)}"
                response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"    응답: {data.get('totalItems', 0)}개 결과")
                    
                    if data.get('totalItems', 0) > 0:
                        for item in data['items'][:3]:  # 상위 3개 결과
                            volume_info = item.get('volumeInfo', {})
                            
                            # ISBN 매칭 확인
                            item_isbns = volume_info.get('industryIdentifiers', [])
                            isbn_found = False
                            
                            for identifier in item_isbns:
                                identifier_value = identifier.get('identifier', '')
                                # ISBN 정확 매칭 또는 부분 매칭
                                if isbn in identifier_value or identifier_value in isbn:
                                    isbn_found = True
                                    break
                            
                            # ISBN이 매칭되지 않으면 제목으로라도 확인
                            if not isbn_found and query == isbn:
                                print(f"    ISBN 매칭 실패하지만 일반 검색 결과 사용")
                                isbn_found = True
                            
                            if isbn_found:
                                book_info = {
                                    'title': volume_info.get('title', 'Unknown'),
                                    'authors': ', '.join(volume_info.get('authors', ['Unknown'])),
                                    'publisher': volume_info.get('publisher', 'Unknown'),
                                    'published_date': volume_info.get('publishedDate', 'Unknown'),
                                    'description': volume_info.get('description', ''),
                                    'thumbnail_url': volume_info.get('imageLinks', {}).get('thumbnail', ''),
                                    'isbn': isbn,
                                    'api_source': f'google_isbn_{query}',
                                    'similarity_score': 1.0 if isbn_found else 0.8
                                }
                                books.append(book_info)
                                print(f"    찾은 책: {book_info['title']} by {book_info['authors']}")
                        
                        if books:
                            print(f"  Google Books 성공: {len(books)}권 찾음")
                            return books
                            
            except Exception as e:
                print(f"    검색 오류 ({query}): {e}")
                continue
        
        print(f"  Google Books ISBN 검색 실패: {isbn}")
        return []
    
    def _search_naver_books_by_isbn(self, isbn):
        """네이버 Books API로 ISBN 검색 - 개선된 검색"""
        if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
            print("  네이버 API 키 없음, 건너뜀")
            return []
        
        # 여러 검색 방법 시도
        search_queries = [
            isbn,                  # 원본 ISBN
            isbn.replace('-', ''), # 하이픈 제거
            f"isbn:{isbn}",       # 명시적 ISBN 검색
        ]
        
        for query in search_queries:
            try:
                print(f"  네이버 검색 시도: {query}")
                url = "https://openapi.naver.com/v1/search/book.json"
                headers = {
                    'X-Naver-Client-Id': NAVER_CLIENT_ID,
                    'X-Naver-Client-Secret': NAVER_CLIENT_SECRET
                }
                params = {
                    'query': query,
                    'display': 5,
                    'start': 1,
                    'sort': 'sim'  # 정확도순
                }
                
                response = requests.get(url, headers=headers, params=params, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    print(f"    응답: {len(items)}개 결과")
                    
                    books = []
                    for item in items:
                        item_isbn = item.get('isbn', '')
                        item_title = self._clean_html_tags(item.get('title', ''))
                        
                        # ISBN 매칭 확인 (더 관대하게)
                        isbn_match = False
                        clean_input_isbn = isbn.replace('-', '').replace(' ', '')
                        clean_item_isbn = item_isbn.replace('-', '').replace(' ', '')
                        
                        if clean_input_isbn and clean_item_isbn:
                            # 전체 매칭 또는 부분 매칭
                            if (clean_input_isbn in clean_item_isbn or 
                                clean_item_isbn in clean_input_isbn or
                                clean_input_isbn == clean_item_isbn):
                                isbn_match = True
                        
                        # 첫 번째 쿼리에서는 모든 결과 포함 (네이버가 관련성 판단)
                        if isbn_match or query == isbn:
                            book_info = {
                                'title': item_title,
                                'authors': self._clean_html_tags(item.get('author', 'Unknown')),
                                'publisher': self._clean_html_tags(item.get('publisher', 'Unknown')),
                                'published_date': item.get('pubdate', 'Unknown'),
                                'description': self._clean_html_tags(item.get('description', '')),
                                'thumbnail_url': item.get('image', ''),
                                'isbn': isbn,
                                'kyobo_link': item.get('link', ''),
                                'api_source': f'naver_isbn_{query}',
                                'similarity_score': 1.0 if isbn_match else 0.8
                            }
                            books.append(book_info)
                            print(f"    찾은 책: {item_title} (ISBN 매칭: {isbn_match})")
                    
                    if books:
                        print(f"  네이버 성공: {len(books)}권 찾음")
                        return books
                        
            except Exception as e:
                print(f"    네이버 검색 오류 ({query}): {e}")
                continue
        
        print(f"  네이버 ISBN 검색 실패: {isbn}")
        return []
    
    def _preprocess_title_for_search(self, title):
        """검색용 제목 전처리 - 부제목, 설명문 제거"""
        if not title:
            return ""
        
        # 괄호 안의 설명문 제거 (너무 긴 설명은 검색 방해)
        # 예: "달리기를 말할 때 내가 하고 싶은 이야기 (세계적 작가 하루키의...)" -> "달리기를 말할 때 내가 하고 싶은 이야기"
        clean_title = re.sub(r'\([^)]{20,}\)', '', title)  # 20자 이상의 긴 설명만 제거
        
        # 하이픈이나 콜론 뒤의 부제목 제거 (단, 너무 짧지 않은 경우만)
        if len(clean_title) > 10:
            # " - ", " : ", " ― " 등으로 구분된 부제목 제거
            patterns = [r'\s*[-:―]\s*[^-:―]{10,}$', r'\s*-\s*[^-]{15,}$']
            for pattern in patterns:
                if re.search(pattern, clean_title):
                    clean_title = re.sub(pattern, '', clean_title)
                    break
        
        # 연속된 공백 정리
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
        
        # 너무 짧아지면 원본 사용
        if len(clean_title) < 3:
            clean_title = title
        
        return clean_title
    
    def _filter_search_results(self, books, original_title):
        """검색 결과 필터링 - 제목 유사성 검증"""
        if not books:
            return books
        
        # 원본 제목에서 핵심 키워드 추출
        original_clean = re.sub(r'[^\w\s가-힣]', ' ', original_title.lower()).strip()
        original_words = set(original_clean.split())
        
        filtered_books = []
        
        for book in books:
            result_title = book.get('title', '').lower()
            result_clean = re.sub(r'[^\w\s가-힣]', ' ', result_title).strip()
            result_words = set(result_clean.split())
            
            # 공통 단어 비율 계산
            if original_words and result_words:
                common_words = original_words.intersection(result_words)
                similarity = len(common_words) / min(len(original_words), len(result_words))
                
                print(f"  유사도 {similarity:.2f}: '{book.get('title')}' by {book.get('authors')}")
                
                # 유사도 0.3 이상만 허용 (30% 이상 단어 일치)
                if similarity >= 0.3:
                    book['similarity_score'] = similarity
                    filtered_books.append(book)
            else:
                # 단어 분석이 불가능한 경우 원본 포함
                book['similarity_score'] = 0.5
                filtered_books.append(book)
        
        # 유사도 순으로 정렬
        filtered_books.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
        
        print(f"  필터링 결과: {len(books)} -> {len(filtered_books)}권")
        return filtered_books
    
    def search_naver_books(self, query):
        """네이버 Books API로 도서 정보 검색"""
        if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
            print("네이버 API 키가 설정되지 않았습니다. Google Books API를 사용합니다.")
            return self.search_google_books(query)
        
        try:
            # 네이버 검색 API 호출
            url = "https://openapi.naver.com/v1/search/book.json"
            headers = {
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET
            }
            params = {
                'query': query,
                'display': 5,  # 최대 5개 결과
                'start': 1,
                'sort': 'sim'  # 정확도순
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                books = []
                
                for item in data.get('items', []):
                    book_info = {
                        'title': self._clean_html_tags(item.get('title', 'Unknown')),
                        'authors': self._clean_html_tags(item.get('author', 'Unknown')),
                        'publisher': self._clean_html_tags(item.get('publisher', 'Unknown')),
                        'published_date': item.get('pubdate', 'Unknown'),
                        'description': self._clean_html_tags(item.get('description', '')),
                        'thumbnail_url': item.get('image', ''),
                        'isbn': item.get('isbn', ''),
                        'api_source': 'naver'
                    }
                    
                    # 네이버 쇼핑에서 교보문고 링크 찾기
                    kyobo_link = self._find_kyobo_link(book_info['title'], book_info['isbn'])
                    if kyobo_link:
                        book_info['kyobo_link'] = kyobo_link
                    
                    books.append(book_info)
                
                return books
            else:
                print(f"네이버 API 오류: {response.status_code}")
                
        except Exception as e:
            print(f"네이버 API 호출 오류: {e}")
        
        return []
    
    def _find_kyobo_link(self, title, isbn):
        """네이버 쇼핑 API를 통해 교보문고 링크 찾기"""
        if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
            return None
        
        try:
            # 네이버 쇼핑 API 호출
            url = "https://openapi.naver.com/v1/search/shop.json"
            headers = {
                'X-Naver-Client-Id': NAVER_CLIENT_ID,
                'X-Naver-Client-Secret': NAVER_CLIENT_SECRET
            }
            
            # ISBN이 있으면 ISBN으로, 없으면 책 제목으로 검색
            search_query = isbn if isbn else title
            params = {
                'query': f"{search_query} 책",
                'display': 10,
                'start': 1,
                'sort': 'sim'
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                
                for item in data.get('items', []):
                    mall_name = item.get('mallName', '').lower()
                    
                    # 교보문고 관련 쇼핑몰 이름 확인
                    if '교보문고' in mall_name or 'kyobobook' in mall_name:
                        return item.get('link', '')
                    
                    # 네이버 쇼핑에서 교보문고로 연결되는 링크 확인
                    link = item.get('link', '')
                    if 'kyobobook' in link.lower():
                        return link
                
        except Exception as e:
            print(f"교보문고 링크 검색 오류: {e}")
        
        return None
    
    def search_google_books(self, query):
        """Google Books API로 도서 정보 검색"""
        try:
            # Google Books API 호출
            url = f"https://www.googleapis.com/books/v1/volumes?q={quote(query)}"
            response = requests.get(url, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('totalItems', 0) > 0:
                    books = []
                    for item in data['items'][:5]:  # 상위 5개 결과만
                        volume_info = item.get('volumeInfo', {})
                        
                        book_info = {
                            'title': volume_info.get('title', 'Unknown'),
                            'authors': ', '.join(volume_info.get('authors', ['Unknown'])),
                            'publisher': volume_info.get('publisher', 'Unknown'),
                            'published_date': volume_info.get('publishedDate', 'Unknown'),
                            'description': volume_info.get('description', ''),
                            'thumbnail_url': volume_info.get('imageLinks', {}).get('thumbnail', ''),
                            'isbn': self._extract_isbn(volume_info.get('industryIdentifiers', [])),
                            'api_source': 'google'
                        }
                        books.append(book_info)
                    
                    return books
                
        except Exception as e:
            print(f"Google Books API 호출 오류: {e}")
        
        return []
    
    def _clean_html_tags(self, text):
        """HTML 태그 제거"""
        if not text:
            return ''
        # HTML 태그 제거
        clean_text = re.sub(r'<[^>]+>', '', str(text))
        return clean_text.strip()
    
    def _extract_isbn(self, identifiers):
        """ISBN 추출"""
        for identifier in identifiers:
            if identifier.get('type') in ['ISBN_13', 'ISBN_10']:
                return identifier.get('identifier', '')
        return ''
    
    def add_book(self, book_info, price=None, notes=''):
        """책 정보 데이터베이스에 추가"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO books (title, authors, publisher, published_date, isbn, 
                             description, thumbnail_url, price, notes, kyobo_link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            book_info['title'],
            book_info['authors'],
            book_info['publisher'],
            book_info['published_date'],
            book_info['isbn'],
            book_info['description'],
            book_info['thumbnail_url'],
            price,
            notes,
            book_info.get('kyobo_link', '')
        ))
        
        conn.commit()
        book_id = cursor.lastrowid
        conn.close()
        
        return book_id
    
    def add_book_simple(self, title, price=None, notes=''):
        """제목만으로 책 추가 (API 호출 없이)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO books (title, authors, publisher, published_date, isbn, 
                             description, thumbnail_url, price, notes, kyobo_link)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            title,
            'Unknown',  # 기본값
            'Unknown',  # 기본값
            'Unknown',  # 기본값
            '',         # 기본값
            '',         # 기본값
            '',         # 기본값
            price,
            notes,
            ''          # 기본값
        ))
        
        conn.commit()
        book_id = cursor.lastrowid
        conn.close()
        
        return book_id
    
    def update_book_details(self, book_id, book_info):
        """책 상세정보 업데이트"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE books SET 
                authors = ?, publisher = ?, published_date = ?, isbn = ?,
                description = ?, thumbnail_url = ?, kyobo_link = ?
            WHERE id = ?
        ''', (
            book_info['authors'],
            book_info['publisher'],
            book_info['published_date'],
            book_info['isbn'],
            book_info['description'],
            book_info['thumbnail_url'],
            book_info.get('kyobo_link', ''),
            book_id
        ))
        
        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()
        
        return rows_affected > 0
    
    def get_all_books(self):
        """모든 책 목록 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, title, authors, publisher, published_date, isbn, 
                   description, thumbnail_url, purchase_date, price, notes, 
                   kyobo_link, created_at 
            FROM books ORDER BY purchase_date DESC
        ''')
        
        books = []
        for row in cursor.fetchall():
            book = {
                'id': row[0],
                'title': row[1],
                'authors': row[2],
                'publisher': row[3],
                'published_date': row[4],
                'isbn': row[5],
                'description': row[6],
                'thumbnail_url': row[7],
                'purchase_date': row[8],
                'price': row[9],
                'notes': row[10],
                'kyobo_link': row[11] if row[11] else '',
                'created_at': row[12]
            }
            books.append(book)
        
        conn.close()
        return books
    
    def delete_book(self, book_id):
        """책 삭제"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 책이 존재하는지 먼저 확인
            cursor.execute('SELECT title FROM books WHERE id = ?', (book_id,))
            book = cursor.fetchone()
            
            if not book:
                conn.close()
                return False, '책을 찾을 수 없습니다'
            
            # 책 삭제
            cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))
            conn.commit()
            
            # 삭제된 행 수 확인
            if cursor.rowcount > 0:
                conn.close()
                return True, f'"{book[0]}" 책이 삭제되었습니다'
            else:
                conn.close()
                return False, '책 삭제에 실패했습니다'
                
        except Exception as e:
            if 'conn' in locals():
                conn.close()
            return False, f'삭제 중 오류가 발생했습니다: {str(e)}'
    
    def check_duplicate(self, title, isbn=None):
        """중복 도서 검사 - 강화된 중복 검사"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. ISBN이 있으면 ISBN 우선 검사
        if isbn and isbn.strip():
            clean_isbn = isbn.strip().replace('-', '').replace(' ', '')
            if clean_isbn:
                cursor.execute('SELECT title FROM books WHERE isbn = ? AND isbn != ""', (isbn,))
                result = cursor.fetchone()
                if result:
                    conn.close()
                    print(f"ISBN 중복 발견: {isbn} -> {result[0]}")
                    return True
                
                # ISBN 정규화해서도 체크
                cursor.execute('SELECT isbn, title FROM books WHERE isbn != ""')
                existing_isbns = cursor.fetchall()
                for existing_isbn, existing_title in existing_isbns:
                    clean_existing = existing_isbn.strip().replace('-', '').replace(' ', '')
                    if clean_isbn == clean_existing:
                        conn.close()
                        print(f"정규화된 ISBN 중복 발견: {clean_isbn} -> {existing_title}")
                        return True
        
        # 2. 제목으로 중복 검사 (더 강화된 방식)
        cursor.execute('SELECT title FROM books')
        existing_titles = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        # 더 엄격한 정규화
        clean_title = self._normalize_title_for_duplicate_check(title)
        
        for existing in existing_titles:
            clean_existing = self._normalize_title_for_duplicate_check(existing)
            if clean_title == clean_existing:
                print(f"제목 중복 발견: '{title}' -> '{existing}'")
                return True
        
        return False
    
    def _normalize_title_for_duplicate_check(self, title):
        """중복 검사용 제목 정규화"""
        import re
        if not title:
            return ""
        
        # 기본 정규화
        normalized = title.strip().lower()
        
        # 공백문자 정규화 (일반 공백, 전각 공백, 탭 등)
        normalized = re.sub(r'\s+', '', normalized)
        
        # 특수문자 제거 (괄호, 하이픈, 콜론 등)
        normalized = re.sub(r'[^\w가-힣]', '', normalized)
        
        # 연속된 문자 정리
        normalized = re.sub(r'(.)\1{2,}', r'\1', normalized)
        
        return normalized
    
    def bulk_add_books(self, book_titles, progress_callback=None):
        """대량 책 추가 - 강화된 오류 처리"""
        results = {
            'success': [],
            'duplicates': [],
            'errors': [],
            'total': len(book_titles)
        }
        
        for i, title in enumerate(book_titles):
            title = title.strip()
            if not title:
                continue
                
            try:
                print(f"처리 중 ({i+1}/{len(book_titles)}): {title[:50]}...")
                
                # 진행률 콜백 호출
                if progress_callback:
                    progress_callback(i + 1, len(book_titles), title)
                
                # 중복 검사
                try:
                    if self.check_duplicate(title):
                        results['duplicates'].append({
                            'title': title,
                            'reason': '이미 등록된 책입니다'
                        })
                        continue
                except Exception as dup_error:
                    print(f"중복 검사 오류: {str(dup_error)}")
                    # 중복 검사 실패해도 계속 진행
                
                # 책 정보 검색 - 더 강력한 재시도 로직
                books = None
                max_retries = 3
                
                for retry in range(max_retries):
                    try:
                        # 타임아웃 시간 단축
                        books = self.search_book_info(title)
                        if books:
                            break
                        else:
                            print(f"검색 결과 없음 (시도 {retry+1}/{max_retries}): {title}")
                    except Exception as search_error:
                        print(f"검색 오류 (시도 {retry+1}/{max_retries}): {str(search_error)}")
                        if retry == max_retries - 1:
                            # 마지막 시도에서도 실패하면 오류로 기록
                            raise search_error
                        # 잠시 대기 후 재시도
                        import time
                        time.sleep(0.5)  # 대기시간 단축
                
                if books and len(books) > 0:
                    try:
                        # 첫 번째 검색 결과 사용
                        book_info = books[0]
                        book_id = self.add_book(book_info)
                        
                        results['success'].append({
                            'title': book_info['title'],
                            'authors': book_info['authors'],
                            'id': book_id
                        })
                        print(f"추가 성공: {book_info['title']}")
                        
                    except Exception as add_error:
                        print(f"DB 추가 오류: {str(add_error)}")
                        results['errors'].append({
                            'title': title,
                            'reason': f'데이터베이스 추가 실패: {str(add_error)}'
                        })
                else:
                    results['errors'].append({
                        'title': title,
                        'reason': '검색 결과가 없습니다'
                    })
                    
            except Exception as e:
                # 상세한 오류 정보 기록
                import traceback
                error_trace = traceback.format_exc()
                print(f"책 처리 중 예외: {title} - {str(e)}")
                print(f"상세 오류: {error_trace}")
                
                results['errors'].append({
                    'title': title,
                    'reason': f'처리 중 오류: {str(e)}'
                })
            
            # 서버 부하 방지를 위한 짧은 대기
            if i > 0 and i % 5 == 0:  # 5권마다 잠시 대기
                import time
                time.sleep(0.1)
        
        print(f"벌크 처리 완료: 성공 {len(results['success'])}, 중복 {len(results['duplicates'])}, 실패 {len(results['errors'])}")
        return results
    
    def bulk_add_books_safe(self, book_titles):
        """안전하게 대량 추가 - ISBN은 제목을 먼저 찾아서 저장"""
        results = {
            'success': [],
            'duplicates': [],
            'errors': [],
            'total': len(book_titles)
        }
        
        for i, query in enumerate(book_titles):
            query = query.strip()
            if not query:
                continue
                
            try:
                print(f"안전 모드 처리 ({i+1}/{len(book_titles)}): {query[:50]}...")
                
                # 대량 추가에서는 ISBN 검색 제거 - 안전 모드로 단순화
                actual_title = query.strip()
                print(f"  안전 모드: 제목 '{actual_title}' 그대로 저장")
                
                # 중복 검사 (실제 제목으로)
                try:
                    if self.check_duplicate(actual_title):
                        results['duplicates'].append({
                            'title': actual_title,
                            'reason': '이미 등록된 책입니다'
                        })
                        continue
                except Exception as dup_error:
                    print(f"  중복 검사 실패, 계속 진행: {str(dup_error)}")
                    # 중복 검사 실패해도 계속 진행
                
                # 실제 제목으로 책 추가
                book_id = self.add_book_simple(actual_title)
                
                results['success'].append({
                    'title': actual_title,
                    'authors': 'Unknown',
                    'id': book_id
                })
                print(f"안전 추가 성공: {actual_title}")
                
            except Exception as e:
                print(f"안전 모드에서도 오류: {query} - {str(e)}")
                results['errors'].append({
                    'title': query,
                    'reason': f'데이터베이스 오류: {str(e)}'
                })
        
        print(f"안전 모드 처리 완료: 성공 {len(results['success'])}, 중복 {len(results['duplicates'])}, 실패 {len(results['errors'])}")
        return results
    
    def bulk_add_books_batch(self, book_titles, batch_size=50):
        """배치 단위로 대량 책 추가 - 435권 같은 대용량 처리용"""
        results = {
            'success': [],
            'duplicates': [],
            'errors': [],
            'total': len(book_titles),
            'processed': 0,
            'batches': []
        }
        
        # 배치로 나누기
        total_books = len(book_titles)
        
        for batch_start in range(0, total_books, batch_size):
            batch_end = min(batch_start + batch_size, total_books)
            batch_titles = book_titles[batch_start:batch_end]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (total_books + batch_size - 1) // batch_size
            
            print(f"배치 {batch_num}/{total_batches} 처리 중... ({len(batch_titles)}권)")
            
            # 각 배치 처리
            batch_results = self.bulk_add_books(batch_titles)
            
            # 결과 합치기
            results['success'].extend(batch_results['success'])
            results['duplicates'].extend(batch_results['duplicates'])
            results['errors'].extend(batch_results['errors'])
            results['processed'] += len(batch_titles)
            
            # 배치별 결과 기록
            results['batches'].append({
                'batch_num': batch_num,
                'total_batches': total_batches,
                'success_count': len(batch_results['success']),
                'duplicate_count': len(batch_results['duplicates']),
                'error_count': len(batch_results['errors'])
            })
            
            # 배치 간 잠시 대기 (서버 부하 방지)
            if batch_end < total_books:
                import time
                time.sleep(2)
        
        return results
    
    def parse_csv_content(self, csv_content):
        """CSV 내용 파싱 - 다중 줄 텍스트 필드 지원"""
        titles = []
        
        try:
            # Python csv 모듈 사용 (다중 줄 텍스트 처리 지원)
            csv_reader = csv.reader(io.StringIO(csv_content), quoting=csv.QUOTE_ALL)
            
            # 헤더 건너뛰기
            header_skipped = False
            
            for row_num, row in enumerate(csv_reader):
                if not row:  # 빈 행 건너뛰기
                    continue
                
                # 첫 번째 행이 헤더인지 확인
                if not header_skipped:
                    first_cell = row[0].strip().lower()
                    if first_cell in ['도서명', '제목', 'title', 'book_title', '책제목']:
                        header_skipped = True
                        continue
                    header_skipped = True
                
                # 첫 번째 컬럼을 책 제목으로 사용
                if len(row) > 0:
                    title = row[0].strip()
                    if title:  # 비어있지 않은 제목만 추가
                        titles.append(title)
                        
        except Exception as e:
            # CSV 파싱 실패시 간단한 라인 단위 파싱으로 대체
            print(f"CSV 파싱 오류 ({str(e)}), 라인 단위 파싱으로 전환")
            return self._parse_csv_fallback(csv_content)
        
        return titles
    
    def _parse_csv_fallback(self, csv_content):
        """CSV 파싱 실패시 대체 방법"""
        titles = []
        lines = csv_content.split('\n')
        
        # 첫 번째 줄이 헤더인지 확인
        first_line_processed = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 첫 번째 라인 헤더 체크
            if not first_line_processed:
                if line.lower().startswith(('도서명', '제목', 'title')):
                    first_line_processed = True
                    continue
                first_line_processed = True
            
            # 쉼표로 분리해서 첫 번째 필드만 추출
            if ',' in line:
                # 따옴표로 둘러싸인 경우 처리
                if line.startswith('"'):
                    # 닫는 따옴표 찾기
                    end_quote = line.find('",', 1)
                    if end_quote > 0:
                        title = line[1:end_quote].strip()
                    else:
                        title = line[1:].rstrip('"').strip()
                else:
                    title = line.split(',')[0].strip()
                
                if title:
                    titles.append(title)
        
        return titles
    
    def parse_text_content(self, text_content):
        """텍스트 내용 파싱 (줄바꿈으로 구분)"""
        titles = []
        lines = text_content.split('\n')
        
        for line in lines:
            title = line.strip()
            if title:
                titles.append(title)
        
        return titles
    
    # ============== 백그라운드 업데이트 작업 메서드들 ==============
    
    def create_update_job(self, total_books):
        """새로운 업데이트 작업 생성"""
        job_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO update_jobs (job_id, status, total_books)
            VALUES (?, 'pending', ?)
        ''', (job_id, total_books))
        
        conn.commit()
        conn.close()
        
        return job_id
    
    def get_update_job_status(self, job_id):
        """업데이트 작업 상태 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT job_id, status, total_books, processed_books, 
                   success_count, error_count, created_at, updated_at, completed_at
            FROM update_jobs 
            WHERE job_id = ?
        ''', (job_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'job_id': row[0],
                'status': row[1],
                'total_books': row[2],
                'processed_books': row[3],
                'success_count': row[4],
                'error_count': row[5],
                'created_at': row[6],
                'updated_at': row[7],
                'completed_at': row[8],
                'progress': (row[3] / row[2] * 100) if row[2] > 0 else 0
            }
        return None
    
    def update_job_progress(self, job_id, processed_books, success_count, error_count, status='processing'):
        """작업 진행 상황 업데이트"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE update_jobs 
            SET processed_books = ?, success_count = ?, error_count = ?, 
                status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        ''', (processed_books, success_count, error_count, status, job_id))
        
        conn.commit()
        conn.close()
    
    def complete_update_job(self, job_id, final_status='completed'):
        """작업 완료 처리"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE update_jobs 
            SET status = ?, completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE job_id = ?
        ''', (final_status, job_id))
        
        conn.commit()
        conn.close()
    
    def log_update_result(self, job_id, book_id, book_title, success, message=""):
        """개별 책 업데이트 결과 로그"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO update_logs (job_id, book_id, book_title, success, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (job_id, book_id, book_title, success, message))
        
        conn.commit()
        conn.close()
    
    def get_update_logs(self, job_id, limit=10):
        """업데이트 로그 조회 (최근 N개)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT book_id, book_title, success, message, created_at
            FROM update_logs 
            WHERE job_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (job_id, limit))
        
        logs = []
        for row in cursor.fetchall():
            logs.append({
                'book_id': row[0],
                'book_title': row[1],
                'success': bool(row[2]),
                'message': row[3],
                'created_at': row[4]
            })
        
        conn.close()
        return logs
    
    def background_update_books(self, job_id):
        """백그라운드에서 Unknown 책들 업데이트"""
        try:
            print(f"백그라운드 업데이트 작업 시작: {job_id}")
            
            # Unknown 상태인 책들 조회
            all_books = self.get_all_books()
            unknown_books = [book for book in all_books if book['authors'] == 'Unknown']
            
            if not unknown_books:
                self.complete_update_job(job_id, 'completed')
                print(f"업데이트할 책이 없음: {job_id}")
                return
            
            success_count = 0
            error_count = 0
            
            for i, book in enumerate(unknown_books):
                try:
                    print(f"[{i+1}/{len(unknown_books)}] 처리 중: {book['title'][:40]}...")
                    
                    # 책 정보 검색
                    books_info = self.search_book_info(book['title'])
                    
                    if books_info and len(books_info) > 0:
                        book_info = books_info[0]
                        update_success = self.update_book_details(book['id'], book_info)
                        
                        if update_success:
                            success_count += 1
                            self.log_update_result(job_id, book['id'], book['title'], True, 
                                                 f"성공: {book_info.get('authors', 'N/A')}")
                            print(f"  ✓ 성공: {book_info.get('authors', 'N/A')}")
                        else:
                            error_count += 1
                            self.log_update_result(job_id, book['id'], book['title'], False, "DB 업데이트 실패")
                            print(f"  ✗ DB 업데이트 실패")
                    else:
                        error_count += 1
                        self.log_update_result(job_id, book['id'], book['title'], False, "검색 결과 없음")
                        print(f"  ✗ 검색 결과 없음")
                        
                except Exception as e:
                    error_count += 1
                    error_msg = str(e)[:100]
                    self.log_update_result(job_id, book['id'], book['title'], False, f"오류: {error_msg}")
                    print(f"  ✗ 오류: {error_msg}")
                
                # 진행 상황 업데이트
                processed = i + 1
                self.update_job_progress(job_id, processed, success_count, error_count, 'processing')
                
                # API 부하 방지
                time.sleep(0.2)
            
            # 작업 완료
            self.complete_update_job(job_id, 'completed')
            print(f"백그라운드 업데이트 완료: {job_id} - 성공 {success_count}, 실패 {error_count}")
            
        except Exception as e:
            print(f"백그라운드 업데이트 오류: {job_id} - {str(e)}")
            self.complete_update_job(job_id, 'failed')
    
    def start_background_update(self):
        """백그라운드 업데이트 작업 시작"""
        # Unknown 책 개수 확인
        all_books = self.get_all_books()
        unknown_books = [book for book in all_books if book['authors'] == 'Unknown']
        
        if not unknown_books:
            return None, "업데이트할 책이 없습니다"
        
        # 작업 생성
        job_id = self.create_update_job(len(unknown_books))
        
        # 백그라운드 스레드로 실행
        thread = threading.Thread(target=self.background_update_books, args=(job_id,))
        thread.daemon = True  # 메인 프로세스 종료 시 함께 종료
        thread.start()
        
        return job_id, f"{len(unknown_books)}권의 업데이트 작업이 시작되었습니다"

# BookTracker 인스턴스 생성
book_tracker = BookTracker()

# Jinja2 커스텀 필터 추가
@app.template_filter('selectattr')
def selectattr_filter(items, attribute, test=None, value=None):
    """selectattr 필터 구현"""
    if test == 'equalto':
        return [item for item in items if item.get(attribute) == value]
    else:
        return [item for item in items if item.get(attribute) is not None]

@app.template_filter('map')
def map_filter(items, attribute):
    """map 필터 구현"""
    return [item.get(attribute) for item in items if item.get(attribute) is not None]

@app.template_filter('sum')
def sum_filter(items):
    """sum 필터 구현"""
    return sum(items)

@app.template_filter('tojsonfilter')
def to_json_filter(obj):
    """JSON 직렬화 필터"""
    return json.dumps(obj, ensure_ascii=False, default=str)

@app.template_filter('urlencode')
def urlencode_filter(text):
    """URL 인코딩 필터"""
    return quote(str(text), safe='')

@app.route('/')
def index():
    """메인 페이지"""
    books = book_tracker.get_all_books()
    return render_template('index.html', books=books)

@app.route('/search', methods=['POST'])
def search():
    """도서 검색"""
    query = request.json.get('query', '').strip()
    
    if not query:
        return jsonify({'error': '검색어를 입력하세요'}), 400
    
    # 언어 감지
    is_korean = book_tracker.detect_language(query)
    api_used = 'naver' if is_korean else 'google'
    
    # 중복 검사
    is_duplicate = book_tracker.check_duplicate(query)
    
    # 도서 정보 검색
    books = book_tracker.search_book_info(query)
    
    return jsonify({
        'books': books,
        'is_duplicate': is_duplicate,
        'duplicate_message': '이미 구매한 책일 수 있습니다!' if is_duplicate else '',
        'query_language': 'korean' if is_korean else 'english',
        'primary_api': api_used,
        'search_info': f"{'한국어' if is_korean else '영어'} 검색어 감지 → {'네이버' if api_used == 'naver' else 'Google'} Books API 사용"
    })

@app.route('/add_book', methods=['POST'])
def add_book():
    """책 추가 - 강화된 중복 방지"""
    try:
        book_info = request.json.get('book_info', {})
        price = request.json.get('price')
        notes = request.json.get('notes', '')
        
        if price:
            try:
                price = float(price)
            except ValueError:
                price = None
        
        # 강화된 중복 검사
        title = book_info.get('title', '').strip()
        isbn = book_info.get('isbn', '').strip()
        
        if not title:
            return jsonify({
                'success': False,
                'error': '책 제목이 필요합니다.'
            }), 400
        
        # 중복 검사 수행
        is_duplicate = book_tracker.check_duplicate(title, isbn)
        
        if is_duplicate:
            return jsonify({
                'success': False,
                'is_duplicate': True,
                'duplicate_title': title,
                'error': f'이미 등록된 책입니다: {title}'
            }), 409  # Conflict status code
        
        # 중복이 아니면 책 추가
        book_id = book_tracker.add_book(book_info, price, notes)
        
        return jsonify({
            'success': True,
            'message': '책이 성공적으로 추가되었습니다!',
            'book_id': book_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'책 추가 중 오류가 발생했습니다: {str(e)}'
        }), 500

@app.route('/books')
def books():
    """책 목록 페이지"""
    books = book_tracker.get_all_books()
    return render_template('books.html', books=books)

@app.route('/delete_book/<int:book_id>', methods=['DELETE'])
def delete_book(book_id):
    """책 삭제 API"""
    try:
        success, message = book_tracker.delete_book(book_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'error': message
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'삭제 처리 중 오류가 발생했습니다: {str(e)}'
        }), 500

@app.route('/bulk_add')
def bulk_add():
    """대량 추가 페이지"""
    return render_template('bulk_add.html')

@app.route('/bulk_add_csv', methods=['POST'])
def bulk_add_csv():
    """CSV 파일 대량 추가 - 강화된 오류 처리"""
    try:
        if 'csv_file' not in request.files:
            return jsonify({'error': 'CSV 파일을 업로드해주세요'}), 400
        
        file = request.files['csv_file']
        if file.filename == '':
            return jsonify({'error': 'CSV 파일을 선택해주세요'}), 400
        
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'CSV 파일만 업로드 가능합니다'}), 400
        
        # 파일 크기 체크 (5MB 제한)
        file.seek(0, 2)  # 파일 끝으로 이동
        file_size = file.tell()
        file.seek(0)  # 파일 처음으로 되돌림
        
        if file_size > 5 * 1024 * 1024:  # 5MB
            return jsonify({'error': 'CSV 파일 크기는 5MB 이하여야 합니다'}), 400
        
        # CSV 내용 읽기 - 여러 인코딩 시도
        csv_content = None
        raw_content = file.read()
        
        for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'latin1']:
            try:
                csv_content = raw_content.decode(encoding)
                print(f"CSV 파일 인코딩 감지: {encoding}")
                break
            except UnicodeDecodeError:
                continue
        
        if csv_content is None:
            return jsonify({'error': 'CSV 파일 인코딩을 읽을 수 없습니다. UTF-8로 저장해주세요'}), 400
        
        # CSV 파싱
        try:
            titles = book_tracker.parse_csv_content(csv_content)
            print(f"CSV 파싱 완료: {len(titles)}개 제목 추출")
        except Exception as parse_error:
            print(f"CSV 파싱 오류: {str(parse_error)}")
            return jsonify({'error': f'CSV 파싱 실패: {str(parse_error)}'}), 400
        
        if not titles:
            return jsonify({'error': 'CSV 파일에서 책 제목을 찾을 수 없습니다'}), 400
        
        # 대용량 처리를 위한 배치 시스템
        if len(titles) > 500:
            return jsonify({'error': '한 번에 최대 500권까지 처리할 수 있습니다. 500권씩 나누어서 처리해주세요'}), 400
        
        # 서버 안정성을 위해 안전 모드 사용 (API 호출 없이 제목만 저장)
        try:
            print(f"안전 모드로 {len(titles)}권 처리 시작 (API 호출 없이 제목만 저장)")
            results = book_tracker.bulk_add_books_safe(titles)
            
            print(f"안전 모드 처리 완료: 성공 {len(results['success'])}권, 오류 {len(results['errors'])}권")
            
        except Exception as process_error:
            print(f"안전 모드에서도 오류: {str(process_error)}")
            import traceback
            print(f"상세 오류: {traceback.format_exc()}")
            
            return jsonify({
                'success': False,
                'error': f'안전 모드에서도 오류가 발생했습니다: {str(process_error)}'
            }), 500
        
        return jsonify({
            'success': True,
            'results': results,
            'message': f'총 {results["total"]}권 처리 완료 (성공: {len(results["success"])}권, 실패: {len(results["errors"])}권)'
        })
        
    except Exception as e:
        # 더 자세한 오류 정보 제공
        import traceback
        error_details = traceback.format_exc()
        print(f"CSV 업로드 최상위 오류: {error_details}")  # 서버 로그용
        
        return jsonify({
            'success': False,
            'error': f'CSV 처리 중 예상치 못한 오류가 발생했습니다: {str(e)}'
        }), 500

@app.route('/bulk_add_text', methods=['POST'])
def bulk_add_text():
    """텍스트 대량 추가"""
    try:
        # JSON 데이터 파싱 오류 처리
        if not request.is_json:
            return jsonify({'error': '잘못된 요청 형식입니다'}), 400
        
        text_content = request.json.get('text_content', '').strip()
        
        if not text_content:
            return jsonify({'error': '책 제목을 입력해주세요'}), 400
        
        # 텍스트 길이 제한 (너무 큰 데이터 방지)
        if len(text_content) > 50000:  # 50KB
            return jsonify({'error': '입력 텍스트가 너무 큽니다. 50KB 이하로 줄여주세요'}), 400
        
        # 텍스트 내용 파싱
        titles = book_tracker.parse_text_content(text_content)
        
        if not titles:
            return jsonify({'error': '유효한 책 제목을 찾을 수 없습니다'}), 400
        
        # 대용량 처리를 위한 배치 시스템
        if len(titles) > 500:
            return jsonify({'error': '한 번에 최대 500권까지 처리할 수 있습니다. 500권씩 나누어서 처리해주세요'}), 400
        
        # 안전 모드로 처리 (API 호출 없이 제목만 저장)
        results = book_tracker.bulk_add_books_safe(titles)
        
        return jsonify({
            'success': True,
            'results': results,
            'message': f'총 {results["total"]}권 처리 완료'
        })
        
    except Exception as e:
        # 더 자세한 오류 정보 제공
        import traceback
        error_details = traceback.format_exc()
        print(f"텍스트 대량 추가 오류: {error_details}")  # 서버 로그용
        
        return jsonify({
            'success': False,
            'error': f'텍스트 처리 중 오류가 발생했습니다: {str(e)}'
        }), 500

@app.route('/update_book_details/<int:book_id>', methods=['POST'])
def update_book_details(book_id):
    """개별 책 상세정보 업데이트"""
    try:
        # 현재 책 정보 조회
        books = book_tracker.get_all_books()
        current_book = None
        for book in books:
            if book['id'] == book_id:
                current_book = book
                break
        
        if not current_book:
            return jsonify({'success': False, 'error': '책을 찾을 수 없습니다'}), 404
        
        # 책 제목으로 API 검색
        books_info = book_tracker.search_book_info(current_book['title'])
        
        if not books_info:
            return jsonify({
                'success': False, 
                'error': '해당 책의 상세정보를 찾을 수 없습니다'
            }), 404
        
        # 첫 번째 검색 결과로 업데이트
        book_info = books_info[0]
        success = book_tracker.update_book_details(book_id, book_info)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'{book_info["title"]} 상세정보가 업데이트되었습니다',
                'book_info': book_info
            })
        else:
            return jsonify({
                'success': False,
                'error': '상세정보 업데이트에 실패했습니다'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'상세정보 업데이트 중 오류: {str(e)}'
        }), 500

@app.route('/smart_update_details', methods=['POST'])
def smart_update_details():
    """스마트 업데이트: 사용자 지정 개수만큼 처리"""
    try:
        data = request.get_json() or {}
        update_count = data.get('count', 5)  # 기본 5권으로 축소 (Railway 30초 제한 고려)
        
        # Unknown 상태인 책들만 필터링
        all_books = book_tracker.get_all_books()
        unknown_books = [book for book in all_books if book['authors'] == 'Unknown']
        
        if not unknown_books:
            return jsonify({
                'success': True,
                'message': '업데이트할 책이 없습니다',
                'results': {'success': 0, 'errors': 0, 'total': 0}
            })
        
        # 지정된 개수만큼만 처리
        books_to_update = unknown_books[:update_count]
        remaining_count = len(unknown_books) - len(books_to_update)
        
        results = {
            'success': [],
            'errors': [],
            'total': len(books_to_update),
            'remaining': remaining_count
        }
        
        print(f"스마트 업데이트: {len(books_to_update)}권 처리 시작")
        
        # Railway 타임아웃 방지를 위한 시간 추적
        import time
        start_time = time.time()
        max_execution_time = 25  # 25초 제한 (Railway 30초 제한 고려)
        
        for i, book in enumerate(books_to_update):
            # 시간 체크 - 너무 오래 걸리면 중단
            if time.time() - start_time > max_execution_time:
                print(f"시간 초과로 인한 조기 종료: {i}권 처리 완료")
                results['remaining'] = len(unknown_books) - i
                break
            try:
                print(f"[{i+1}/{len(books_to_update)}] 업데이트: {book['title'][:40]}...")
                
                books_info = book_tracker.search_book_info(book['title'])
                
                if books_info and len(books_info) > 0:
                    book_info = books_info[0]
                    success = book_tracker.update_book_details(book['id'], book_info)
                    
                    if success:
                        results['success'].append({
                            'id': book['id'],
                            'title': book['title'],
                            'authors': book_info.get('authors', 'Unknown'),
                            'publisher': book_info.get('publisher', 'Unknown')
                        })
                        print(f"  ✓ 성공: {book_info.get('authors', 'N/A')}")
                    else:
                        results['errors'].append({
                            'title': book['title'],
                            'reason': 'DB 업데이트 실패'
                        })
                        print(f"  ✗ DB 실패")
                else:
                    results['errors'].append({
                        'title': book['title'],
                        'reason': '검색 결과 없음'
                    })
                    print(f"  ✗ 검색 실패")
                    
            except Exception as e:
                results['errors'].append({
                    'title': book['title'],
                    'reason': f'오류: {str(e)[:30]}'
                })
                print(f"  ✗ 오류: {str(e)}")
            
            # API 부하 방지 - Railway 타임아웃 고려하여 대기시간 축소
            import time
            time.sleep(0.1)
        
        success_count = len(results['success'])
        error_count = len(results['errors'])
        
        message = f'업데이트 완료: 성공 {success_count}권, 실패 {error_count}권'
        if remaining_count > 0:
            message += f' (남은 Unknown 책: {remaining_count}권)'
        
        return jsonify({
            'success': True,
            'message': message,
            'results': results
        })
        
    except Exception as e:
        print(f"스마트 업데이트 오류: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'스마트 업데이트 오류: {str(e)}'
        }), 500

@app.route('/bulk_update_details', methods=['POST'])
def bulk_update_details():
    """Unknown 상태인 책들의 상세정보 대량 업데이트 - 배치 처리로 안정성 향상"""
    try:
        # Unknown 상태인 책들만 필터링
        all_books = book_tracker.get_all_books()
        unknown_books = [book for book in all_books if book['authors'] == 'Unknown']
        
        if not unknown_books:
            return jsonify({
                'success': True,
                'message': '업데이트할 책이 없습니다 (모든 책의 상세정보가 이미 있음)',
                'results': {'success': 0, 'errors': 0, 'total': 0}
            })
        
        # 배치 설정: Railway HTTP 타임아웃(30초) 고려하여 5권씩 처리
        batch_size = 5
        total_books = len(unknown_books)
        
        results = {
            'success': [],
            'errors': [],
            'total': total_books,
            'batches': []
        }
        
        print(f"대량 업데이트 시작: {total_books}권을 {batch_size}권씩 배치 처리")
        
        # 배치 단위로 처리
        for batch_start in range(0, total_books, batch_size):
            batch_end = min(batch_start + batch_size, total_books)
            batch_books = unknown_books[batch_start:batch_end]
            current_batch = (batch_start // batch_size) + 1
            total_batches = (total_books + batch_size - 1) // batch_size
            
            batch_results = {
                'batch_num': current_batch,
                'total_batches': total_batches,
                'success_count': 0,
                'error_count': 0
            }
            
            print(f"배치 {current_batch}/{total_batches} 처리 시작 ({len(batch_books)}권)")
            
            # 배치 내 각 책 처리
            for local_idx, book in enumerate(batch_books):
                global_idx = batch_start + local_idx + 1
                
                try:
                    print(f"  [{global_idx}/{total_books}] 업데이트: {book['title'][:40]}...")
                    
                    # API 검색 (타임아웃 짧게 설정)
                    books_info = book_tracker.search_book_info(book['title'])
                    
                    if books_info and len(books_info) > 0:
                        book_info = books_info[0]
                        
                        # 데이터베이스 업데이트
                        success = book_tracker.update_book_details(book['id'], book_info)
                        
                        if success:
                            results['success'].append({
                                'id': book['id'],
                                'title': book['title'],
                                'authors': book_info.get('authors', 'Unknown'),
                                'publisher': book_info.get('publisher', 'Unknown')
                            })
                            batch_results['success_count'] += 1
                            print(f"    ✓ 성공: {book_info.get('authors', 'N/A')}")
                        else:
                            results['errors'].append({
                                'id': book['id'],
                                'title': book['title'],
                                'reason': 'DB 업데이트 실패'
                            })
                            batch_results['error_count'] += 1
                            print(f"    ✗ DB 업데이트 실패")
                    else:
                        results['errors'].append({
                            'id': book['id'],
                            'title': book['title'],
                            'reason': '검색 결과 없음'
                        })
                        batch_results['error_count'] += 1
                        print(f"    ✗ 검색 결과 없음")
                        
                except Exception as e:
                    error_msg = str(e)
                    results['errors'].append({
                        'id': book['id'],
                        'title': book['title'],
                        'reason': f'오류: {error_msg[:50]}'
                    })
                    batch_results['error_count'] += 1
                    print(f"    ✗ 오류: {error_msg}")
                
                # 개별 책 처리 간 짧은 대기 (API 부하 방지)
                import time
                time.sleep(0.1)
            
            # 배치 결과 저장
            results['batches'].append(batch_results)
            print(f"배치 {current_batch} 완료: 성공 {batch_results['success_count']}, 실패 {batch_results['error_count']}")
            
            # 배치 간 대기 (서버 부하 방지)
            if current_batch < total_batches:
                time.sleep(0.5)
        
        success_count = len(results['success'])
        error_count = len(results['errors'])
        
        print(f"대량 업데이트 완료: 성공 {success_count}권, 실패 {error_count}권")
        
        return jsonify({
            'success': True,
            'message': f'대량 업데이트 완료: 성공 {success_count}권, 실패 {error_count}권 (총 {total_books}권)',
            'results': results
        })
        
    except Exception as e:
        error_msg = str(e)
        print(f"대량 업데이트 시스템 오류: {error_msg}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': f'시스템 오류 발생: {error_msg}'
        }), 500

# ============== 백그라운드 업데이트 API 엔드포인트들 ==============

@app.route('/start_background_update', methods=['POST'])
def start_background_update():
    """백그라운드 업데이트 작업 시작"""
    try:
        job_id, message = book_tracker.start_background_update()
        
        if job_id:
            return jsonify({
                'success': True,
                'job_id': job_id,
                'message': message
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'백그라운드 업데이트 시작 실패: {str(e)}'
        }), 500

@app.route('/update_status/<job_id>', methods=['GET'])
def get_update_status(job_id):
    """업데이트 작업 상태 조회"""
    try:
        job_status = book_tracker.get_update_job_status(job_id)
        
        if job_status:
            # 최근 로그도 함께 반환
            recent_logs = book_tracker.get_update_logs(job_id, limit=5)
            job_status['recent_logs'] = recent_logs
            
            return jsonify({
                'success': True,
                'status': job_status
            })
        else:
            return jsonify({
                'success': False,
                'error': '작업을 찾을 수 없습니다'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'상태 조회 실패: {str(e)}'
        }), 500

@app.route('/update_logs/<job_id>', methods=['GET'])
def get_update_logs_api(job_id):
    """업데이트 로그 조회"""
    try:
        limit = request.args.get('limit', 20, type=int)
        logs = book_tracker.get_update_logs(job_id, limit=limit)
        
        return jsonify({
            'success': True,
            'logs': logs
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'로그 조회 실패: {str(e)}'
        }), 500

if __name__ == '__main__':
    # 로컬 개발용
    app.run(debug=True, host='127.0.0.1', port=8082)