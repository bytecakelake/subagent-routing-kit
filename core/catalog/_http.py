"""수집기 공용 HTTP 클라이언트(httpx).

urllib 과 달라서 맞춰 둔 동작:
- 리다이렉트: urllib 은 따라가지만 httpx 는 기본으로 따라가지 않는다 -> follow_redirects=True.
- HTTP 오류: urllib 은 4xx/5xx 에서 예외를 던지지만 httpx 는 응답을 돌려준다 -> get_bytes 가 raise_for_status 를 호출한다.
- 재시도: httpx 의 transport retries 는 연결 오류만 재시도하고 5xx 는 재시도하지 않는다. 여기서는 재시도하지 않는다.
httpx.Client 는 스레드 안전하므로 한 클라이언트를 여러 스레드가 공유해 연결을 재사용한다.
"""
import httpx


def new_client(timeout):
    return httpx.Client(timeout=timeout, follow_redirects=True)


def get_bytes(client, url):
    r = client.get(url)
    r.raise_for_status()
    return r.content


def describe(exc):
    """오류를 한 줄로. httpx 예외는 str() 이 비어 있는 경우가 있어 종류를 항상 붙인다."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return f"{type(exc).__name__}: {exc}".rstrip(": ")
