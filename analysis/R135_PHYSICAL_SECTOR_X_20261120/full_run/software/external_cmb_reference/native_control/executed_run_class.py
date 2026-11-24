def run_class(class_input, source_root, output, *, YHe):
    """Call the pinned CLASS binary for an explicitly established native model."""
    from .observations import validate_class_model
    if class_input.get("perturbation_model",{}).get("kind")=="class_ethos_idm_idr":
        from .perturbations import validate_ethos_input
        doc=validate_ethos_input(class_input)
        actual_model="native CLASS elastic ETHOS IDM-IDR perturbation equations"
    else:
        doc = validate_class_model(class_input)
        actual_model="standard native CLASS free-streaming radiation after matching"
    source = verify_checkout(source_root, PINS["class"])
    binary = Path(source_root).resolve() / "class"
    if not binary.is_file():
        raise OpenInput("the pinned CLASS checkout has not been built")
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache_key = canonical_hash({"input": class_input, "YHe": YHe, "source": source["source_commit"],
                                "binary_sha256": sha256(binary), "adapter_sha256": sha256(Path(__file__))})
    if (out / "receipt.json").exists():
        receipt = read_json(out / "receipt.json")
        if receipt.get("input_cache_key") != cache_key:
            raise InputError("CLASS cache belongs to a different history, model or code")
        for name, digest in receipt["files"].items():
            if sha256(out / name) != digest:
                raise InputError("cached CLASS artifact changed")
        return read_json(out / "spectra.json"), {**receipt, "cache_reused": True}
    if any(out.iterdir()):
        raise InputError("CLASS has an incomplete checkpoint; preserve it and use a new isolated output directory")
    pars = dict(doc["parameters"])
    pars.update(doc["precision"])
    pars["YHe"] = finite(YHe, "BBN helium mass fraction", positive=True)
    if pars["YHe"] >= 1:
        raise InputError("helium fraction must be below one")
    lmax=doc["l_max_scalars"]
    pars.update({"N_ncdm": 0, "output": "tCl,pCl,lCl", "lensing": "yes", "l_max_scalars": lmax,
                 "root": str(out / "spectra_"), "headers": "yes", "format": "camb", "write background": "yes"})
    parameter_file = out / "parameters.ini"
    parameter_file.write_text("".join(f"{k} = {v}\n" for k, v in pars.items()))
    with (out / "CLASS.log").open("w") as log:
        subprocess.run([str(binary), str(parameter_file)], cwd=source_root,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    files = list(out.glob("*cl_lensed.dat"))
    if len(files) != 1:
        raise RuntimeError("CLASS did not produce the requested lensed CMB spectra")
    table = np.loadtxt(files[0])
    ell = table[:, 0]
    if not np.array_equal(ell, np.arange(2, lmax+1)) or table.shape[1] < 5 or not np.isfinite(table).all():
        raise RuntimeError("CLASS output has invalid multipole coverage or nonfinite values")
    # In CAMB format CLASS writes l(l+1)Cl/(2pi) in microkelvin squared:
    # ell, TT, EE, BB, TE. Do not apply the (Tcmb*1e6)^2 conversion twice.
    factor = 2 * np.pi / (ell * (ell + 1))
    spectra = {"ell": ell.astype(int).tolist(), "unit": "microK^2", "convention": "Cl", "lensed":True,
               **{name: (table[:, i] * factor).tolist() for i, name in enumerate(("TT", "EE", "BB", "TE"), 1)}}
    from .likelihood import validate_spectra
    validate_spectra(spectra)
    write_json(out / "spectra.json", spectra)
    receipt = {"source": source, "input_cache_key": cache_key, "cache_reused": False,
               "binary_sha256": sha256(binary), "parameters_sha256": sha256(parameter_file),
               "source_P7_history_sha256": class_input.get("source_P7_history_sha256"),
               "spectra_sha256": sha256(out / "spectra.json"), "input": doc, "matching": class_input.get("matching"),
               "actual_model": actual_model,
               "files": {p.name: sha256(p) for p in out.iterdir() if p.is_file()}}
    write_json(out / "receipt.json", receipt)
    return spectra, receipt
