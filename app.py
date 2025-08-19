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

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# 파일 업로드 크기 제한 (5MB)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# JSON 요청 크기 제한
app.config['MAX_CONTENT_PATH'] = 5 * 1024 * 1024

# 네이버 API 설정 (환경변수 또는 직접 설정)
NAVER_CLIENT_ID = os.getenv('NAVER_CLIENT_ID', '')  # 네이버 개발자센터에서 발급
NAVER_CLIENT_SECRET = os.getenv('NAVER_CLIENT_SECRET', '')  # 네이버 개발자센터에서 발급

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
        """언어별 API 선택하여 도서 정보 검색"""
        is_korean = self.detect_language(query)
        
        if is_korean:
            # 한국어 제목: 네이버 Books API 사용
            books = self.search_naver_books(query)
            if not books:
                # 네이버에서 결과가 없으면 Google Books API도 시도
                books = self.search_google_books(query)
        else:
            # 영어 제목: Google Books API 사용
            books = self.search_google_books(query)
            if not books:
                # Google에서 결과가 없으면 네이버 API도 시도
                books = self.search_naver_books(query)
        
        return books
    
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
        """중복 도서 검사"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if isbn:
            cursor.execute('SELECT * FROM books WHERE isbn = ? AND isbn != ""', (isbn,))
            result = cursor.fetchone()
            if result:
                conn.close()
                return True
        
        # 제목으로 유사도 검사 (간단한 문자열 매칭)
        cursor.execute('SELECT title FROM books')
        existing_titles = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        # 간단한 중복 검사 (대소문자 무시, 공백 제거)
        clean_title = title.lower().replace(' ', '').replace('　', '')
        for existing in existing_titles:
            clean_existing = existing.lower().replace(' ', '').replace('　', '')
            if clean_title in clean_existing or clean_existing in clean_title:
                return True
        
        return False
    
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
        """API 호출 없이 제목만으로 안전하게 대량 추가"""
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
                print(f"안전 모드 처리 ({i+1}/{len(book_titles)}): {title[:50]}...")
                
                # 중복 검사
                try:
                    if self.check_duplicate(title):
                        results['duplicates'].append({
                            'title': title,
                            'reason': '이미 등록된 책입니다'
                        })
                        continue
                except Exception as dup_error:
                    print(f"중복 검사 실패, 계속 진행: {str(dup_error)}")
                    # 중복 검사 실패해도 계속 진행
                
                # API 호출 없이 제목만으로 추가
                book_id = self.add_book_simple(title)
                
                results['success'].append({
                    'title': title,
                    'authors': 'Unknown',
                    'id': book_id
                })
                print(f"안전 추가 성공: {title}")
                
            except Exception as e:
                print(f"안전 모드에서도 오류: {title} - {str(e)}")
                results['errors'].append({
                    'title': title,
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

# BookTracker 인스턴스 생성
book_tracker = BookTracker()

# Jinja2 커스텀 필터 추가
@app.template_filter('selectattr')
def selectattr_filter(items, attribute):
    """selectattr 필터 구현"""
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
    """책 추가"""
    try:
        book_info = request.json.get('book_info', {})
        price = request.json.get('price')
        notes = request.json.get('notes', '')
        
        if price:
            try:
                price = float(price)
            except ValueError:
                price = None
        
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

if __name__ == '__main__':
    # 로컬 개발용
    app.run(debug=True, host='127.0.0.1', port=8082)