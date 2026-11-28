"""Small deterministic one/two-Gaussian diagnostic, without a new dependency.

BIC and component responsibilities describe intensities, not PNC identity.
Spatially correlated pixels invalidate biological probability/FPR claims.
Unimodal/nonconvergent fits return no mixture-derived signal, never a forced call.
"""

import numpy as np
from scipy.special import logsumexp

ALGORITHM = "one-two-intensity-gaussian-bic-v1"


def fit_intensity_mixture(values, *, max_samples=1024, max_iterations=80):
    values = np.asarray(values, dtype=float).ravel()
    if not len(values) or not np.isfinite(values).all():
        raise ValueError("Mixture input must contain finite intensities")
    # Deterministic evenly spaced spatial samples bound work, not establish independence.
    values = values[np.linspace(0, len(values)-1, min(len(values), max_samples), dtype=int)]
    center, scale = float(np.median(values)), float(np.std(values))
    fallback = {"algorithm": ALGORITHM, "threshold": None, "samples": len(values),
                "bic_one": None, "bic_two": None, "iterations": 0,
                "fallback": "no mixture-derived signal", "spatial_independence": "not assumed"}
    if len(values) < 16 or scale <= max(abs(center)*1e-8, 1e-12):
        return {**fallback, "status": "constant_or_insufficient_values"}
    x = (values-center)/scale
    variance = max(float(np.var(x)), 1e-6)
    ll_one = float(np.sum(-.5*(np.log(2*np.pi*variance)+(x-x.mean())**2/variance)))
    bic_one = -2*ll_one + 2*np.log(len(x))
    best = None
    for tail in (.01, .1, .3):
        means = np.percentile(x, [40, 100*(1-tail/2)])
        variances = np.full(2, variance)
        weights = np.array([1-tail, tail])
        previous = -np.inf
        converged = False
        for iteration in range(max_iterations):
            log_density = (np.log(weights) - .5*np.log(2*np.pi*variances)
                           - (x[:, None]-means)**2/(2*variances))
            normalizer = logsumexp(log_density, axis=1)
            likelihood = float(normalizer.sum())
            if abs(likelihood-previous) <= 1e-6*(1+abs(likelihood)):
                converged = True
                break
            if likelihood < previous-1e-5:
                break
            previous = likelihood
            responsibility = np.exp(log_density-normalizer[:, None])
            mass = responsibility.sum(axis=0)
            weights = np.maximum(mass/len(x), 1e-6)
            weights /= weights.sum()
            means = (responsibility*x[:, None]).sum(axis=0)/np.maximum(mass, 1e-9)
            variances = np.maximum((responsibility*(x[:, None]-means)**2).sum(axis=0)/np.maximum(mass, 1e-9), 1e-4)
        if converged and (best is None or likelihood > best[0]):
            order = np.argsort(means)
            best = likelihood, means[order], variances[order], weights[order], iteration+1
    fallback["bic_one"] = float(bic_one)
    if best is None:
        return {**fallback, "status": "nonconvergence"}
    likelihood, means, variances, weights, iterations = best
    bic_two = -2*likelihood + 5*np.log(len(x))
    fallback.update(bic_two=float(bic_two), iterations=iterations,
                    component_means=list(map(float, means*scale+center)),
                    high_component_weight=float(weights[1]))
    if bic_two+10 >= bic_one or weights[1] > .5 or means[1]-means[0] < .5*np.sqrt(variances[0]):
        return {**fallback, "status": "one_component_or_weak_separation"}
    # Decision boundary of intensity components; not a biological posterior cutoff.
    a = .5*(1/variances[0]-1/variances[1])
    b = means[1]/variances[1]-means[0]/variances[0]
    c = (np.log(weights[1]/weights[0])-.5*np.log(variances[1]/variances[0])
         +means[0]**2/(2*variances[0])-means[1]**2/(2*variances[1]))
    roots = np.roots([a, b, c]) if abs(a) > 1e-9 else np.roots([b, c])
    usable = [float(r.real) for r in roots if abs(r.imag) < 1e-8 and means[0] < r.real < means[1]]
    if not usable:
        return {**fallback, "status": "no_separating_intensity_boundary"}
    return {**fallback, "status": "two_components_diagnostic", "threshold": min(usable)*scale+center,
            "fallback": None}
