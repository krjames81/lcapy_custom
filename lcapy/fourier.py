"""This module provides support for Fourier transforms.  It acts as a
wrapper for SymPy's Fourier transform.  It calculates the bilateral
Fourier transform using:

   S(f) = \int_{-\infty}^{\infty} s(t) e^{-j * 2* \pi * t} dt

It also allows functions that strictly do not have a Fourier transform
by using Dirac deltas.  For example, a, cos(a * t), sin(a * t), exp(j
* a * t).


Copyright 2016--2019 Michael Hayes, UCECE

"""

# TODO:
# Add DiracDelta(t, n)
# Simplify  (-j * DiracDelta(f - 1) +j * DiracDelta(f + 1)).inverse_fourier()
# This should give 2 * sin(2 * pi * t)


import sympy as sym

fourier_cache = {}

def factor_const(expr, t):

    # Perhaps use expr.as_coeff_Mul() ?
    
    rest = sym.S.One
    const = sym.S.One
    for factor in expr.as_ordered_factors():
        # Cannot use factor.is_constant() since Sympy 1.2, 1.3
        # barfs for Heaviside(t) and DiracDelta(t)
        if not factor.has(t):
            const *= factor
        else:
            rest *= factor
    return const, rest


def scale_shift(expr, t):

    if not expr.has(t):
        raise ValueError('Expression does not contain %s: %s' % (t, expr))

    terms = expr.as_ordered_terms()
    if len(terms) > 2:
        raise ValueError('Expression has too many terms: %s' % expr)

    if len(terms) == 1:
        return terms[0] / t, sym.S.Zero

    scale = terms[0] / t
    if not scale.is_constant():
        raise ValueError('Expression not a scale and shift: %s' % expr)

    return scale, terms[1]
    
    
def fourier_sympy(expr, t, f):

    result = sym.fourier_transform(expr, t, f)
    if expr != 0 and result == 0:
        # There is a bug in SymPy where it returns 0.
        raise ValueError('Could not compute Fourier transform for ' + str(expr))

    if isinstance(result, sym.FourierTransform):
        raise ValueError('Could not compute Fourier transform for ' + str(expr))
    
    return result


def fourier_func(expr, t, f, inverse=False):

    if not isinstance(expr, sym.function.AppliedUndef):
        raise ValueError('Expecting function for %s' % expr)

    scale, shift = scale_shift(expr.args[0], t)

    fsym = sym.sympify(str(f))
    
    # Convert v(t) to V(f), etc.
    name = expr.func.__name__
    if inverse:
        func = name[0].lower() + name[1:] + '(%s)' % f
    else:
        func = name[0].upper() + name[1:] + '(%s)' % f

    result = sym.sympify(func).subs(fsym, f / scale) / abs(scale)

    if shift != 0:
        if inverse:
            shift = -shift
        result = result * sym.exp(2j * sym.pi * f * shift / scale)
    
    return result


def fourier_function(expr, t, f, inverse=False):

    # Handle expressions with a function of FOO, e.g.,
    # v(t), v(t) * y(t),  3 * v(t) / t, v(4 * a * t), etc.,
    
    if not expr.has(sym.function.AppliedUndef):
        raise ValueError('Could not compute Fourier transform for ' + str(expr))

    const, expr = factor_const(expr, t)
    
    fsym = sym.sympify(str(f))

    if isinstance(expr, sym.function.AppliedUndef):
        return fourier_func(expr, t, f, inverse) * const
    
    tsym = sym.sympify(str(t))
    expr = expr.subs(tsym, t)

    rest = sym.S.One
    undefs = []
    for factor in expr.as_ordered_factors():
        if isinstance(factor, sym.function.AppliedUndef):
            if factor.args[0] != t:
                raise ValueError('Weird function %s not of %s' % (factor, t))
            undefs.append(factor)
        else:
            rest *= factor

    if rest.has(sym.function.AppliedUndef):
        # Have something like 1/v(t)
        raise ValueError('Cannot compute Fourier transform of %s' % rest)
            
    exprs = undefs
    if rest.has(t):
        exprs = exprs + [rest]
        rest = sym.S.One

    result = fourier_term(exprs[0], t, f, inverse) * rest
        
    if len(exprs) == 1:
        return result * const

    dummy = 'tau' if inverse else 'nu'

    for m in range(len(exprs) - 1):
        if m == 0:
            nu = sym.sympify(dummy)
        else:
            nu = sym.sympify(dummy + '_%d' % m)
        expr2 = fourier_term(exprs[m + 1], t, f, inverse)
        result = sym.Integral(result.subs(f, f - nu) * expr2.subs(f, nu),
                              (nu, -sym.oo, sym.oo))
    
    return result * const

def fourier_term(expr, t, f, inverse=False):

    # TODO add u(t) <-->  delta(f) / 2 - j / (2 * pi * f)
    
    if expr.has(sym.function.AppliedUndef):
        # Handle v(t), v(t) * y(t),  3 * v(t) / t etc.
        return fourier_function(expr, t, f, inverse)

    sf = -f if inverse else f
    
    # Check for constant.
    if not expr.has(t):
        return expr * sym.DiracDelta(f)

    one = sym.S.One
    const = one
    other = one
    exps = one
    factors = expr.as_ordered_factors()    
    for factor in factors:
        if not factor.has(t):
            const *= factor
        else:
            if factor.is_Function and factor.func == sym.exp:
                exps *= factor
            else:
                other *= factor

    if other != 1 and exps == 1:
        if other == t:
            return const * sym.I * 2 * sym.pi * sym.DiracDelta(f, 1)
        if other == t**2:
            return const * (sym.I * 2 * sym.pi)**2 * sym.DiracDelta(f, 2)

        # Sympy incorrectly gives exp(-a * t) instead of exp(-a * t) *
        # Heaviside(t)
        if other.is_Pow and other.args[1] == -1:
            foo = other.args[0]
            if foo.is_Add and foo.args[1].has(t):
                bar = foo.args[1] / t
                if not bar.has(t) and bar.has(sym.I):
                    a = -(foo.args[0] * 2 * sym.pi * sym.I) / bar
                    return const * sym.exp(-a * sf) * sym.Heaviside(sf * sym.sign(a))

        # Punt and use SymPy.  Should check for t**n, t**n * exp(-a * t), etc.
        return fourier_sympy(expr, t, sf)

    args = exps.args[0]
    foo = args / t
    if foo.has(t):
        # Have exp(a * t**n), SymPy might be able to handle this
        return fourier_sympy(expr, t, sf)

    if exps != 1 and foo.has(sym.I):
        return const * sym.DiracDelta(sf - foo / (sym.I * 2 * sym.pi))
        
    return fourier_sympy(expr, t, sf)


def fourier_transform(expr, t, f, inverse=False):
    """Compute bilateral Fourier transform of expr.

    Undefined functions such as v(t) are converted to V(f)

    This also handles some expressions that do not really have a Fourier
    transform, such as a, cos(a * t), sin(a * t), exp(I * a * t).

    """

    key = (expr, t, f, inverse)
    if key in fourier_cache:
        return fourier_cache[key]
    
    if inverse:
        t, f = f, t

    # The variable may have been created with different attributes,
    # say when using sym.sympify('DiracDelta(t)') since this will
    # default to assuming that t is complex.  So if the symbol has the
    # same representation, convert to the desired one.
    var = sym.Symbol(str(t))
    expr = expr.replace(var, t)

    orig_expr = expr

    if expr.has(sym.cos) or expr.has(sym.sin):
        expr = expr.rewrite(sym.exp)

    terms = expr.expand().as_ordered_terms()
    result = 0

    try:
        for term in terms:
            result += fourier_term(term, t, f, inverse=inverse)
    except ValueError:
        raise ValueError('Could not compute Fourier transform for ' + str(orig_expr))

    fourier_cache[key] = result
    return result


def inverse_fourier_transform(expr, f, t):
    """Compute bilateral inverse Fourier transform of expr.

    Undefined functions such as V(f) are converted to v(t)

    This also handles some expressions that do not really have an
    inverse Fourier transform, such as a, cos(a * f), sin(a * f), exp(I *
    a * f).

    """

    result = fourier_transform(expr, t, f, inverse=True)
    return sym.simplify(result)


def test():

     t, f, a = sym.symbols('t f a', real=True)
     a = sym.symbols('a', positive=True)

     print(fourier_transform(a, t, f))
     print(fourier_transform(sym.exp(-sym.I * 2 * sym.pi * a * t), t, f))
     print(fourier_transform(sym.cos(2 * sym.pi * a * t), t, f))
     print(fourier_transform(sym.sin(2 * sym.pi * a * t), t, f))
     print(fourier_transform(a * t, t, f))
     print(fourier_transform(sym.exp(-a * t) * sym.Heaviside(t), t, f))
     print(inverse_fourier_transform(a, f, t))
     print(inverse_fourier_transform(1 / (sym.I * 2 * sym.pi * f + a), f, t))
