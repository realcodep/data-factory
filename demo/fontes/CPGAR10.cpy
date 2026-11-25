      *================================================================*
      * CPGAR10 - LAYOUT DA GARANTIA IMOBILIARIA (FICTICIO - DEMO)     *
      *================================================================*
       01  CPGAR10-REGISTRO.
           05 GAR-ID                   PIC 9(09).
           05 GAR-TIPO                 PIC X(03).
              88 GAR-TIPO-IMOVEL       VALUE 'IMO'.
           05 GAR-MATRICULA            PIC X(20).
           05 GAR-VLR-AVALIACAO        PIC S9(13)V99 COMP-3.
           05 GAR-CPF-CNPJ             PIC X(14).
           05 GAR-DT-AVALIACAO         PIC X(10).
           05 GAR-SITUACAO             PIC X(01).
              88 GAR-ATIVA             VALUE 'A'.
              88 GAR-BLOQUEADA         VALUE 'B'.
              88 GAR-EXCLUIDA          VALUE 'E'.
           05 GAR-MOTIVO-BLOQ          PIC X(03).
              88 GAR-MOTIVO-JUDICIAL   VALUE 'JUD'.
              88 GAR-MOTIVO-ADMIN      VALUE 'ADM'.
              88 GAR-MOTIVO-FRAUDE     VALUE 'FRA'.
