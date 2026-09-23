# Changelog

## [v1.4.0] - 23/09/2026

### Solicitado por: Natália

- **Demanda:** Saber para qual obra a mercadoria foi entregue e quem fez o transporte.
- **Implementação técnica:**
  - Extração nativa de XML (`xml.etree.ElementTree`) no endpoint `/nfes`.
  - Captura das tags `infCpl` (endereço de entrega da obra) e `transporta` (nome da transportadora).
  - Vínculo direto ao pedido via `xPed`.

### Corrigido

- Ajuste de timeout e controle de pacing (1.5s) em `/processos`.
