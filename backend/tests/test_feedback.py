"""Gravação da sugestão sem subir o servidor."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.feedback_handler import FeedbackError, registrar_sugestao


class FeedbackTests(unittest.TestCase):
    def test_acrescenta_item_pendente_com_id(self):
        destino = Path(self.id().replace(".", "_") + "_sugestoes.json")
        try:
            primeiro = registrar_sugestao(
                {
                    "modulo": "Ficha do Cliente",
                    "tipo": "Sugestão de funcionalidade",
                    "descricao": "Mostrar a obra logo no card.",
                    "prioridade": "Alta (Trava meu trabalho)",
                    "data": "2026-09-23T13:00:00Z",
                    "autor": "Natália",
                },
                destino,
            )
            segundo = registrar_sugestao(
                {
                    "modulo": "Dashboard",
                    "tipo": "Ajuste visual/usabilidade",
                    "descricao": "O botão de melhoria ficou baixo no celular.",
                    "prioridade": "Baixa",
                    "data": "2026-09-23T13:15:00+00:00",
                    "autor": "Natália",
                },
                destino,
            )
            gravado = json.loads(destino.read_text(encoding="utf-8"))
        finally:
            destino.unlink(missing_ok=True)
        self.assertEqual(primeiro["id"], 1)
        self.assertEqual(segundo["id"], 2)
        self.assertEqual(primeiro["prioridade"], "Alta")
        self.assertEqual(primeiro["status"], "Pendente")
        self.assertEqual(primeiro["resposta_tecnica"], "")
        self.assertEqual(primeiro["autor"], "Natália")
        self.assertEqual(len(primeiro["data"]), 16)
        self.assertEqual(len(gravado), 2)

    def test_recusa_descricao_vazia(self):
        with self.assertRaises(FeedbackError):
            registrar_sugestao(
                {
                    "modulo": "Outro",
                    "tipo": "Inconsistência de dado",
                    "descricao": "   ",
                    "prioridade": "Média",
                    "data": "2026-09-23T13:00:00Z",
                    "autor": "Natália",
                },
                Path("nao_deve_gravar.json"),
            )


if __name__ == "__main__":
    unittest.main()
