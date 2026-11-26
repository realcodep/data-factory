package br.demo.garantias.api.dto;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.LocalDate;

/** DTO fictício (demo) da inclusão de garantia imobiliária. */
public class GarantiaImobiliariaRequest {

    @NotBlank
    @Size(max = 20)
    @Pattern(regexp = "\\d{6,10}")
    private String matriculaImovel;

    @NotNull
    @DecimalMin("1000.00")
    @Digits(integer = 13, fraction = 2)
    private BigDecimal valorAvaliacao;

    @NotNull
    @PastOrPresent
    private LocalDate dataAvaliacao;

    @NotBlank
    @Size(max = 14)
    private String cpfCnpjProprietario;
}
