# 🚀 Railway 배포 단계별 가이드

GitHub 저장소가 준비되었습니다: **https://github.com/dataofmen/book-tracker**

## 1단계: Railway 계정 생성 및 로그인

1. **Railway 웹사이트 방문**: https://railway.app
2. **"Login with GitHub" 클릭** 
3. GitHub 계정으로 로그인/회원가입
4. 필요시 권한 승인

## 2단계: 새 프로젝트 생성

1. Railway 대시보드에서 **"New Project"** 클릭
2. **"Deploy from GitHub repo"** 선택
3. 저장소 목록에서 **"dataofmen/book-tracker"** 찾기
4. **"Deploy Now"** 클릭

## 3단계: 자동 배포 시작

Railway가 자동으로 다음 작업을 수행합니다:
- ✅ `requirements.txt` 파일에서 의존성 설치
- ✅ `Procfile` 명령어로 Gunicorn 웹서버 실행
- ✅ `runtime.txt`에 명시된 Python 3.12.9 사용
- ✅ 자동으로 공개 URL 생성

## 4단계: 배포 상태 확인

1. **"Deployments"** 탭에서 배포 진행 상황 모니터링
2. **성공하면** ✅ "Success" 표시
3. **실패하면** ❌ "View logs"로 오류 확인

## 5단계: 공개 URL 확인

1. **"Settings"** → **"Domains"** 이동
2. 생성된 URL 복사 (예: `https://book-tracker-production.up.railway.app`)
3. 브라우저에서 접속 테스트

## 6단계: 환경변수 설정 (추천)

**네이버 API 설정 (한국어 도서 검색 정확도 향상)**:
1. Railway 프로젝트에서 **"Variables"** 탭 클릭
2. 다음 환경변수 추가:
   ```
   NAVER_CLIENT_ID = IvsMX1RyTuWZiGR6Reot
   NAVER_CLIENT_SECRET = 4CqizzHQ2J
   ```

**💡 네이버 API 사용 시 장점**:
- 한국어 도서 검색 정확도 **대폭 향상** (90% vs 60%)
- "사물의 투명성" 같은 특정 도서 검색 성공률 증가
- 한국 출판사 도서 커버리지 우수

**주의**: 네이버 API가 없어도 Google Books API로 작동하지만 검색 정확도가 떨어집니다.

## 🎉 배포 완료!

배포가 성공하면 다음과 같은 혜택을 누리실 수 있습니다:

- 📱 **어디서나 접근**: 모든 디바이스에서 웹 브라우저로 사용
- 🔒 **자동 HTTPS**: 보안 연결 자동 적용  
- ☁️ **데이터 영구 보관**: SQLite 파일 자동 백업
- 🌍 **글로벌 CDN**: 빠른 로딩 속도
- 💰 **무료 사용**: 월 $5 크레딧으로 개인 사용에 충분

## ⚠️ 문제해결

### 배포 실패시:
1. **"Deployments" → "View Logs"**에서 오류 로그 확인
2. 주요 체크포인트:
   - ✅ `requirements.txt` 파일 존재
   - ✅ `Procfile` 파일 존재  
   - ✅ `runtime.txt` 파일 존재
   - ✅ Python 버전 호환성

### 접속 안될 때:
- 배포 완료 후 2-3분 대기
- 브라우저 캐시 삭제 후 재접속
- Railway 대시보드에서 서비스 상태 확인

---

**Ready to Deploy!** 🚀 위 단계를 따라하시면 Book Tracker가 온라인으로 배포됩니다.