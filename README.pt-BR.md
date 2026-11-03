# Início rápido

`csv-schema-audit` verifica um CSV local contra um schema explícito. Não infere tipos, não corrige dados, não executa fórmulas e não faz chamadas de rede. Os exemplos são inteiramente fictícios.

O template de origem fornece dois stubs editáveis, que precisam ser substituídos para uma versão aceita. Somente uma implementação que passe todos os testes públicos e o oráculo independente pode ser aceita; passar os testes do scaffold não conclui o produto. Esta documentação descreve o contrato, não atesta o estado de um checkout.

Depois de instalar uma wheel aceita:

```text
csv-schema-audit --schema examples/schema.json examples/valid.csv
csv-schema-audit --schema examples/schema.json examples/invalid.csv
```

O primeiro retorna0 e um relatório válido; o segundo retorna1 com required/type_mismatch, sem ecoar valores. Erros de uso/arquivo/schema/UTF-8/motor retornam2 com mensagem fixa no stderr e stdout vazio. `--help` mostra a sintaxe. CSV omitido ou `-` lê stdin, sempre com limite de65.536 bytes. Schema é um arquivo JSON de até16.384 bytes.

As colunas devem existir na ordem declarada. required refere-se à célula vazia, não a uma coluna opcional. Tipos: string, integer, decimal e boolean (apenas true/false). enum compara strings exatas após validar o tipo. Não há trim, conversão numérica, normalização Unicode, reparo ou suporte a planilhas. Os relatórios mostram somente códigos e índices.

A CLI POSIX aceita apenas arquivos regulares e rejeita symlink no componente final; não afirma bloquear symlinks em diretórios pais. Limites inclusivos adicionais:1.000 registros,32 campos,4.096 bytes por campo e100 erros armazenados. Consulte README.md/CONTRACT.txt para precedência e contrato completos.

O helper offline verifica fonte e wheel instalada em namespaces separados sem rede/home/auth, preservando hashes. A opção --scaffold-only é diagnóstico parcial, nunca qualificação do candidato. Nenhuma dependência é instalada no host por esse helper; ferramentas de build precisam estar disponíveis nas versões fixadas.
