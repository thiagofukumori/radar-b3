"""Executa a coleta diária (fase 1). Uso:  .venv\\Scripts\\python.exe coletar.py [--sem-analistas]"""
import sys
from datetime import datetime

from radar.coleta_analistas import coletar_consenso
from radar.coleta_cvm import coletar_fatos
from radar.coleta_noticias import coletar_noticias
from radar.sentimento import classificar_pendentes
from radar.coleta_macro import coletar_macro
from radar.coleta_precos import coletar_precos
from radar.config import DB_PATH
from radar.db import conectar


def _log(con, etapa, ok, falhas):
    con.execute(
        "INSERT INTO log_coleta VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), etapa, ok, len(falhas), "; ".join(falhas)),
    )
    print(f"[{etapa}] ok={ok} falhas={len(falhas)}" + (f" -> {', '.join(falhas)}" if falhas else ""))


def main():
    with conectar() as con:
        ok, falhas, n = coletar_precos(con)
        _log(con, "precos", ok, falhas)
        print(f"         {n} candles gravados")

        if "--sem-analistas" not in sys.argv:
            ok, falhas = coletar_consenso(con)
            _log(con, "analistas", ok, falhas)

        n, falhas = coletar_macro(con)
        _log(con, "macro", n, falhas)

        n, falhas = coletar_noticias(con)
        _log(con, "noticias", n, falhas)
        n, modo = classificar_pendentes(con)
        print(f"         {n} manchetes classificadas ({modo})")

        try:
            n, sem_nome = coletar_fatos(con)
            _log(con, "cvm", n, [f"{t} (nome CVM ambíguo)" for t in sem_nome])
        except Exception as e:
            _log(con, "cvm", 0, [type(e).__name__])
    print(f"Banco: {DB_PATH}")


if __name__ == "__main__":
    main()
