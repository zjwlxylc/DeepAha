"""Optional adapter: mount this router in the EXISTING DeepAha FastAPI app.

No new login/account system. get_principal must call the host's real auth/RBAC and
return security.Principal with a server-controlled producer namespace. This file
contains an executable router, not a guessed import of the user's repository.
"""
from .contract import parse_json
from .errors import ImporterError
from .http_api import API_PREFIX, MAX_BODY, Router


def create_router(service, get_principal):
    from fastapi import APIRouter, Depends, Request
    from fastapi.responses import JSONResponse
    router = APIRouter(prefix=API_PREFIX, tags=['source-intelligence-import'])
    dispatcher = Router(service)

    async def invoke(request: Request, principal, path):
        try:
            body = {}
            if request.method == 'POST':
                if request.headers.get('content-type', '').split(';')[0].strip() != 'application/json':
                    raise ImporterError('CONTENT_TYPE', '请求需要 application/json。', 415)
                raw = bytearray()
                async for chunk in request.stream():
                    raw.extend(chunk)
                    if len(raw) > MAX_BODY:
                        raise ImporterError('SIZE_LIMIT', '请求体超过限制。', 413)
                body = parse_json(bytes(raw), MAX_BODY)
            # DB-API calls are synchronous; don't block the application's async event loop.
            from starlette.concurrency import run_in_threadpool
            result = await run_in_threadpool(dispatcher.dispatch, request.method, path, body, principal)
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except ImporterError as exc:
            return JSONResponse(exc.as_dict(), status_code=exc.status, headers={'Cache-Control': 'no-store'})
        except Exception:
            return JSONResponse(ImporterError('SERVER_ERROR', '无法确认结果，请查询批次回执。', 500).as_dict(), status_code=500)

    @router.get('/capabilities')
    async def capabilities(request: Request, principal=Depends(get_principal)):
        return await invoke(request, principal, '/capabilities')

    @router.post('/preview')
    async def preview(request: Request, principal=Depends(get_principal)):
        return await invoke(request, principal, '/preview')

    @router.post('/commit')
    async def commit(request: Request, principal=Depends(get_principal)):
        return await invoke(request, principal, '/commit')

    @router.get('/batches/by-run/{run_key}')
    async def receipt(run_key: str, request: Request, principal=Depends(get_principal)):
        return await invoke(request, principal, '/batches/by-run/' + run_key)

    return router
