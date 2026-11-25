package br.demo.garantias.api.dto;

import jakarta.validation.constraints.*;

/** DTO fictício (demo) do bloqueio de garantia. */
public class BloqueioRequest {

    public enum MotivoBloqueio { JUD, ADM, FRA }

    @NotNull
    private MotivoBloqueio motivoBloqueio;
}
