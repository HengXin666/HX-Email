from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="HX Email")

    @app.get("/health")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "hx-email"}

    return app


app = create_app()
