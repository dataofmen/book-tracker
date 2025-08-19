# 🚀 Railway 배포 가이드

이 가이드는 Book Tracker를 Railway에 무료로 배포하는 방법을 안내합니다.

## 📋 사전 준비

### 1. GitHub 계정 및 저장소 준비
```bash
# 1. GitHub에서 새 저장소 생성 (예: book-tracker)
# 2. 로컬 프로젝트를 GitHub에 업로드

cd /path/to/book-tracker
git init
git add .
git commit -m "Initial commit: Book Tracker with bulk add feature"
git remote add origin https://github.com/yourusername/book-tracker.git
git branch -M main
git push -u origin main
```

### 2. Railway 계정 생성
- https://railway.app 접속
- GitHub 계정으로 로그인/회원가입

## 🚀 배포 단계

### 단계 1: Railway에서 새 프로젝트 생성
1. Railway 대시보드에서 **"New Project"** 클릭
2. **"Deploy from GitHub repo"** 선택
3. 방금 생성한 GitHub 저장소 선택
4. **"Deploy Now"** 클릭

### 단계 2: 환경변수 설정 (선택사항)
네이버 API를 사용하려면:

1. Railway 프로젝트 대시보드에서 **"Variables"** 탭 클릭
2. 다음 환경변수 추가:
   ```
   NAVER_CLIENT_ID = your_actual_client_id
   NAVER_CLIENT_SECRET = your_actual_client_secret
   ```

**주의**: 네이버 API 키가 없어도 Google Books API만으로 정상 작동합니다!

### 단계 3: 배포 확인
1. **"Deployments"** 탭에서 배포 상태 확인
2. 성공하면 Railway가 자동으로 URL 생성
3. **"Settings"** → **"Domains"** 에서 공개 URL 확인

## 📱 배포된 애플리케이션 사용

### 기본 기능
- 책 제목 검색 및 자동 등록
- 중복 구매 방지
- 언어별 최적화된 API (한국어/영어)

### 대량 추가 기능
1. **CSV 파일 업로드**:
   - 첫 번째 컬럼에 책 제목 입력
   - UTF-8 인코딩 권장
   
2. **텍스트 일괄 입력**:
   - 한 줄에 책 제목 하나씩
   - 복사-붙여넣기로 간편 추가

## 🔧 문제해결

### 배포 실패시
1. **로그 확인**: Railway 대시보드의 "Deployments" → "View Logs"
2. **파일 확인**: 
   - `requirements.txt` (의존성)
   - `Procfile` (실행 명령어)
   - `runtime.txt` (Python 버전)

### 데이터베이스 관련
- SQLite 파일은 Railway의 영구 스토리지에 저장됩니다
- 데이터가 사라지지 않습니다

### API 관련
- 네이버 API 키가 없으면 Google Books API만 사용
- 정상 작동에는 문제없습니다

## 💡 추가 설정

### 커스텀 도메인 (선택사항)
1. Railway 대시보드 → "Settings" → "Domains"
2. "Custom Domain" 추가
3. DNS 설정 필요

### 데이터 백업
정기적으로 책 목록을 CSV로 내보내기 권장 (향후 기능 추가 예정)

## 📊 Railway 무료 플랜 제한

- **월 $5 크레딧**: 개인 사용에 충분
- **자동 슬립**: 비활성시 자동 대기 모드
- **빠른 재시작**: 접속시 즉시 활성화

## 🔒 보안 주의사항

- API 키는 반드시 환경변수로 설정
- GitHub에 `.env` 파일 업로드 금지 (`.gitignore`에 포함됨)
- 정기적인 패스워드 변경 권장

---

배포 완료 후 URL을 통해 어디서나 Book Tracker를 사용할 수 있습니다! 🎉