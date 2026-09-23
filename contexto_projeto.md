# Contexto do Projeto: CRMER
O CRMER é um CRM customizado desenvolvido para a EHE Indústria (fabricante B2B de caixas e abrigos metálicos para construção civil — saneamento, gás, elétrica e fechamento).
A usuária principal do time de vendas é a vendedora Natália. O sistema terá integração em duas fases com o ERP Nomus Industrial e arquitetura modular adaptável para entidades do terceiro setor.

## Stack Tecnológica
- **Front-end:** HTML5 semântico, CSS3 moderno (variáveis CSS, flexbox/grid, layout responsivo e limpo) e JavaScript Vanilla (ES6+ modular).
- **Back-end (futuro/paralelo):** Python (FastAPI) com banco SQLite/PostgreSQL.
- **Integração:** API REST / Webhooks do ERP Nomus Industrial (testados e mapeados via Postman).

## Diretrizes de Design e Usabilidade
- **Foco no Vendedor:** Telas enxutas, baixo atrito de digitação e poucos cliques para registrar atendimentos e follow-ups.
- **Identidade Visual:** Profissional, limpa, estilo dashboard corporativo/industrial, boa tipografia e espaçamento consistente.
- **Feedback Visual Claro:** Destaque para prazos de contato vencidos ou orçamentos aguardando resposta.

## Estrutura de Negócio e Telas Principais
1. **Autenticação:** Login (usuário/e-mail + senha) e cadastro de novo usuário.
2. **Dashboard de Vendas:**
   - Métricas do Usuário Logado: Faturamento do mês, meta, orçamentos em aberto, follow-ups para o dia.
   - Indicadores Compartilhados da EHE: Faturamento global da equipe, volume por linha (Gás, Saneamento, Elétrica).
3. **Gestão de Carteira de Clientes:**
   - Classificação em 4 Rankings Prioritários:
     a) Clientes que devem receber contato (follow-up pendente/agendado para hoje ou atrasado).
     b) Clientes aguardando resposta (orçamentos enviados sem retorno recente).
     c) Clientes que compram nesta época (padrão histórico/sazonal de obras).
     d) Clientes importantes inativos (clientes curva A/B sem compras recentes).
   - Modal/Drawer de Edição do Cliente: Dados cadastrais, histórico de pedidos (vindos do Nomus) e bloco de anotações personalizadas da Natália.

## Padrões de Código para o Cursor
- Mantenha o código limpo, modular e comentado em português quando necessário.
- Separe claramente responsabilidades (`index.html`, `styles.css`, `app.js` ou módulos JS).
- Na etapa inicial de protótipo, utilize dados simulados (mock data) contextualizados com a rotina da EHE Indústria (ex.: Construtora Alfa, Instaladora Beta, pedidos de caixas de gás/hidrômetro).
- Prefira soluções nativas em JavaScript/CSS antes de sugerir bibliotecas externas pesadas.