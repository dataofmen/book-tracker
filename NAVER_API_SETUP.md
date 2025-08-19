# 네이버 Books API 설정 가이드

## 1. 네이버 개발자센터 애플리케이션 등록

### 1-1. 네이버 개발자센터 접속
- https://developers.naver.com/ 접속
- 네이버 계정으로 로그인

### 1-2. 애플리케이션 등록
1. **Applications** 메뉴 클릭
2. **애플리케이션 등록** 버튼 클릭
3. 다음 정보 입력:

```
애플리케이션 이름: Book Tracker
사용 API: 검색 (필수 선택)
환경 추가: PC웹
서비스 URL: http://localhost:8080 (또는 실제 도메인)
```

### 1-3. API 키 발급 확인
- 등록 완료 후 **Client ID**와 **Client Secret** 확인

## 2. 환경변수 설정

### 2-1. 환경변수 파일 생성
```bash
# .env.example을 .env로 복사
cp .env.example .env
```

### 2-2. API 키 설정
`.env` 파일을 열고 실제 키값으로 변경:

```env
NAVER_CLIENT_ID=your_actual_client_id
NAVER_CLIENT_SECRET=your_actual_client_secret
```

### 2-3. 환경변수 로드 (선택사항)
Python-dotenv 라이브러리 사용시:

```bash
pip install python-dotenv
```

`app.py`에 추가:
```python
from dotenv import load_dotenv
load_dotenv()
```

## 3. 직접 설정 방법

환경변수를 사용하지 않는 경우, `app.py` 파일에서 직접 설정:

```python
# 네이버 API 설정
NAVER_CLIENT_ID = 'your_actual_client_id'
NAVER_CLIENT_SECRET = 'your_actual_client_secret'
```

## 4. 테스트

### 4-1. 한국어 검색 테스트
- "파이썬" 검색 → 네이버 API 사용 확인
- "클린 코드" 검색 → 네이버 API 사용 확인

### 4-2. 영어 검색 테스트
- "Clean Code" 검색 → Google Books API 사용 확인
- "Python" 검색 → Google Books API 사용 확인

## 5. API 사용량 확인

### 5-1. 네이버 개발자센터
- **Applications** → 해당 앱 클릭
- **통계** 탭에서 사용량 확인

### 5-2. 사용량 제한
- 검색 API: 하루 25,000회, 초당 10회
- 제한 초과시 HTTP 429 에러 발생

## 6. 문제해결

### Q: 네이버 API 키가 없으면 어떻게 되나요?
A: Google Books API만 사용됩니다. 한국어 검색시에도 Google Books API가 사용됩니다.

### Q: API 호출이 실패하면 어떻게 되나요?
A: 자동으로 다른 API(네이버↔구글)로 fallback하여 검색을 시도합니다.

### Q: 검색 결과가 없으면 어떻게 되나요?
A: 주 API에서 결과가 없으면 자동으로 보조 API를 시도합니다.

## 7. 보안 주의사항

- API 키를 GitHub에 업로드하지 마세요
- `.env` 파일은 `.gitignore`에 추가하세요
- 운영환경에서는 환경변수로 관리하세요