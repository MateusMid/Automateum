# Painel

Parte da [Documentação](README.md).

## Referência Visual

O painel de referência que serviu de ponto de partida:

![Referência do Painel](anexos/painel-referencia.jpeg)

## Características da Interface

- Fundo escuro com grade sutil e tipografia monoespaçada
- Cartões com cantos em colchete, indicador visual de status e texto explicativo sucinto
- Colunas estruturadas:
  - `[01] MÁQUINA`
  - `[02] SERVIÇOS`
  - `[03] FRENTES`
  - `[04] ROTINAS`
  - `[05] COM VOCÊ`
- Fios curvos tracejados e animados interligando as colunas, refletindo o fluxo e o estado dos componentes
- Etiqueta `RAIZ` no cartão onde um problema se inicia, acompanhado da causa
- Latência em milissegundos reportada junto a cada serviço
- Controles interativos na base: arrastar para mover o canvas, rolagem para zoom e botão **Encaixar**

## Recursos Interativos

- **Painel lateral ao clicar no cartão:** histórico de execuções, log de console detalhado, itens coletados e ação **Rodar agora**
- **Atualização em tempo real (SSE):** indicadores visuais de processamento enquanto a rotina executa e transição de cor automática ao finalizar, sem recarregamento de página

## Fluxo do Mapa

O fluxo visual propaga-se da esquerda para a direita. Um traço vermelho ou âmbar mapeia a propagação de falha: do serviço indisponível para a frente afetada e as rotinas suspensas. Cartões em tom cinza representam serviços ou rotinas aguardando configuração de credenciais.
