# VMS Market Data API

这是只读的 A 股行情后端，使用 AkShare 获取沪深 A 股列表和指数数据，并提供分页、搜索和短时缓存。

## Endpoints

- `GET /health`
- `GET /api/stocks?page=1&page_size=50&search=茅台`
- `GET /api/stocks/{code}`
- `GET /api/indices`

## Local run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:CORS_ORIGINS="http://localhost:5173,https://xbq12396.github.io"
uvicorn app.main:app --reload
```

## Deployment

`render.yaml` and `Dockerfile` are included for Render. Set `CORS_ORIGINS` to the exact frontend origin and keep `QUOTE_CACHE_TTL_SECONDS` at or above 30 seconds to reduce pressure on the upstream source.

AkShare aggregates public data sources and does not itself grant a production data license. The service is read-only and intentionally has no order, account, payment, leverage, or funding endpoints. Use a licensed market-data provider for production.
