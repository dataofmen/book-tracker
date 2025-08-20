#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import BookTracker

def test_book_search():
    """사물의 투명성 검색 테스트"""
    tracker = BookTracker()
    
    test_titles = [
        "사물의 투명성",
        "파이썬",
        "클린 코드"
    ]
    
    for title in test_titles:
        print(f"\n{'='*50}")
        print(f"🔍 검색 테스트: '{title}'")
        print(f"{'='*50}")
        
        try:
            results = tracker.search_book_info(title)
            
            if results:
                print(f"✅ 검색 성공: {len(results)}개 결과")
                for i, book in enumerate(results[:3], 1):
                    print(f"  {i}. {book.get('title')} - {book.get('authors')}")
                    print(f"     출판사: {book.get('publisher')}")
                    if book.get('similarity_score'):
                        print(f"     유사도: {book.get('similarity_score'):.2f}")
                    print()
            else:
                print(f"❌ 검색 실패: 결과 없음")
                
        except Exception as e:
            print(f"❌ 검색 오류: {str(e)}")

if __name__ == '__main__':
    test_book_search()