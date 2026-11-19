"""Carrega (ou atualiza) a barbearia a partir do JSON preenchido.

    cd backend
    FIRESTORE_EMULATOR_HOST=localhost:8080 python -m scripts.seed            # emulador
    python -m scripts.seed --real --project SEU-PROJETO                       # Firestore de verdade

Rodar de novo com o arquivo alterado ATUALIZA: barbeiros/serviços com o mesmo nome são
atualizados, novos são criados e os que saíram do arquivo são desativados.
"""

import argparse
import os
import sys

from google.cloud import firestore

from app.repo.firestore_repo import FirestoreRepository
from app.seed import DEFAULT_FILE, apply_shop_data, load


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT_ID", "navalha-dev"))
    ap.add_argument("--file", default=str(DEFAULT_FILE))
    ap.add_argument("--real", action="store_true", help="permite gravar em projeto real (sem emulador)")
    a = ap.parse_args()
    if not os.environ.get("FIRESTORE_EMULATOR_HOST") and not a.real:
        print("FIRESTORE_EMULATOR_HOST não definido. Para gravar no projeto real, use --real.", file=sys.stderr)
        return 2
    repo = FirestoreRepository(firestore.Client(project=a.project))
    shop = apply_shop_data(repo, load(a.file))
    sid = shop["id"]
    print(f"ok: {shop['name']} · id={sid} · link /{shop['slug']}")
    for col in ("barbers", "services"):
        for d in repo.list(col, sid):
            extra = f"{d['commissionPct']}%" if col == "barbers" else f"R$ {d['price'] / 100:.2f} · {d['durationMin']} min"
            print(f"  {col[:-1]:8} {'ativo  ' if d.get('active', True) else 'inativo'} {d['name']} · {extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
