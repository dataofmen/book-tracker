# Book Tracker

회사 법인 카드로 책을 중복 구매하지 않도록 도와주는 개인 도서 관리 시스템입니다.

## ✨ 새로운 기능: 스마트 API 선택

### 🧠 언어별 최적화된 검색
- **한국어 제목** → **네이버 Books API** 사용
- **영어 제목** → **Google Books API** 사용
- **자동 언어 감지**: 검색어의 한글/영문을 자동 판별
- **Fallback 시스템**: 주 API 실패시 자동으로 보조 API 시도

## 주요 기능

### 📚 스마트 서지 정보 수집
- **언어별 최적화된 API 사용**: 한국어 제목은 네이버 Books API, 영어 제목은 Google Books API
- **자동 언어 감지**: 검색어의 언어를 자동으로 판별하여 최적의 API 선택
- **Fallback 시스템**: 주 API에서 결과가 없으면 자동으로 보조 API 시도
- 제목, 저자, 출판사, 출간일, ISBN, 책 표지, 소개글 등 자동 수집

### 🚨 중복 구매 방지
- 이미 보유한 책인지 자동으로 검사
- ISBN 및 제목 기반 중복 검사
- 중복 가능성이 있을 때 경고 메시지 표시

### 💰 구매 이력 관리
- 구매 날짜, 가격 정보 저장
- 총 구매 금액 통계 제공
- 개인 메모 및 후기 저장 가능

### 🔍 검색 및 필터링
- 제목, 저자명으로 빠른 검색
- 가격 정보 유무, 메모 유무, 구매 시기별 필터링
- 다양한 정렬 옵션 (최신순, 제목순, 저자순)

## 설치 및 실행

### 1. 의존성 설치
```bash
cd book-tracker
pip install -r requirements.txt
```

### 2. 네이버 API 설정 (선택사항)
한국어 도서 검색 품질 향상을 위해 네이버 API 키를 설정할 수 있습니다.

```bash
# 환경 설정 파일 복사
cp .env.example .env

# .env 파일을 열고 네이버 API 키 입력
# NAVER_CLIENT_ID=your_client_id
# NAVER_CLIENT_SECRET=your_client_secret
```

📋 **네이버 API 키 발급 방법**: [NAVER_API_SETUP.md](NAVER_API_SETUP.md) 참고

### 3. 애플리케이션 실행
```bash
python app.py
```

### 4. 웹 브라우저에서 접속
```
http://localhost:8080
```

## 사용법

### 📖 책 등록하기
1. 홈페이지에서 책 제목 입력 (한국어/영어 자동 감지)
2. 사용된 API 정보 확인 (파란색 정보 박스)
3. 검색 결과에서 해당 책 선택
4. 구매 가격과 메모 입력 (선택사항)
5. "책 추가" 버튼 클릭

### 📋 책 목록 확인하기
1. 상단 메뉴에서 "책 목록" 클릭
2. 검색, 필터, 정렬 기능 활용
3. "상세보기"로 책 정보 확인

### 🔍 검색 예시
- **한국어**: "파이썬", "클린 코드", "이펙티브 자바" → 네이버 API 사용
- **영어**: "Clean Code", "Python", "Effective Java" → Google Books API 사용

## 기술 스택

- **Backend**: Python Flask
- **Database**: SQLite
- **Frontend**: Bootstrap 5, jQuery
- **APIs**: 
  - 네이버 Books API (한국어 최적화)
  - Google Books API (영어 최적화)
- **Icons**: Font Awesome

## API 우선순위

### 한국어 검색어
1. **1순위**: 네이버 Books API (한국 도서에 최적화)
2. **2순위**: Google Books API (Fallback)

### 영어 검색어
1. **1순위**: Google Books API (국제 도서에 최적화)
2. **2순위**: 네이버 Books API (Fallback)

### API 키가 없는 경우
- 네이버 API 키가 없으면 모든 검색에서 Google Books API 사용
- 애플리케이션은 정상적으로 동작하며 기능 제한 없음

## 데이터베이스 구조

```sql
CREATE TABLE books (
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
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 주의사항

### 네이버 Books API
- 발급받은 API 키가 있으면 더 정확한 한국어 도서 검색 가능
- API 키 없이도 정상 동작 (Google Books API 사용)
- 일일 사용량 제한: 25,000회

### Google Books API
- 별도 인증 없이 사용 가능
- 영어 도서 및 국제 도서에 최적화
- 무료 사용량 제한 있음

### 데이터 보안
- 개인 사용 목적으로 설계되었습니다
- API 키는 환경변수로 관리하세요
- 데이터베이스 파일(`books.db`) 백업을 권장합니다

## 🌐 온라인 배포

### Railway 무료 배포
이 애플리케이션은 Railway를 통해 무료로 온라인 배포할 수 있습니다.

📋 **배포 가이드**: [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md) 참고

**주요 장점**:
- 무료 호스팅 (월 $5 크레딧)
- 자동 HTTPS
- 글로벌 CDN
- 어디서나 접근 가능

## 향후 개선 계획

- [ ] 책 정보 수정/삭제 기능
- [ ] 카테고리/태그 시스템
- [ ] 읽음 상태 관리
- [ ] 데이터 내보내기/가져오기
- [ ] 모바일 앱 지원
- [ ] 알라딘 API 추가 연동
- [x] **Railway 배포 지원** ✨

## 라이선스

개인 사용 목적으로 자유롭게 사용하세요.