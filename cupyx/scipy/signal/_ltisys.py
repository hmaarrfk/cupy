"""
ltisys -- a collection of classes and functions for modeling linear
time invariant systems.
"""
import copy

import cupy

from cupyx.scipy import linalg
from cupyx.scipy.interpolate import make_interp_spline

from cupyx.scipy.signal._lti_conversion import (
    _atleast_2d_or_none, abcd_normalize)
from cupyx.scipy.signal._iir_filter_conversions import (
    normalize, tf2zpk, tf2ss, zpk2ss, ss2tf, ss2zpk, zpk2tf)
from cupyx.scipy.signal._filter_design import freqz, freqz_zpk


class LinearTimeInvariant:
    def __new__(cls, *system, **kwargs):
        """Create a new object, don't allow direct instances."""
        if cls is LinearTimeInvariant:
            raise NotImplementedError('The LinearTimeInvariant class is not '
                                      'meant to be used directly, use `lti` '
                                      'or `dlti` instead.')
        return super().__new__(cls)

    def __init__(self):
        """
        Initialize the `lti` baseclass.

        The heavy lifting is done by the subclasses.
        """
        super().__init__()

        self.inputs = None
        self.outputs = None
        self._dt = None

    @property
    def dt(self):
        """Return the sampling time of the system, `None` for `lti` systems."""
        return self._dt

    @property
    def _dt_dict(self):
        if self.dt is None:
            return {}
        else:
            return {'dt': self.dt}

    @property
    def zeros(self):
        """Zeros of the system."""
        return self.to_zpk().zeros

    @property
    def poles(self):
        """Poles of the system."""
        return self.to_zpk().poles

    def _as_ss(self):
        """Convert to `StateSpace` system, without copying.

        Returns
        -------
        sys: StateSpace
            The `StateSpace` system. If the class is already an instance of
            `StateSpace` then this instance is returned.
        """
        if isinstance(self, StateSpace):
            return self
        else:
            return self.to_ss()

    def _as_zpk(self):
        """Convert to `ZerosPolesGain` system, without copying.

        Returns
        -------
        sys: ZerosPolesGain
            The `ZerosPolesGain` system. If the class is already an instance of
            `ZerosPolesGain` then this instance is returned.
        """
        if isinstance(self, ZerosPolesGain):
            return self
        else:
            return self.to_zpk()

    def _as_tf(self):
        """Convert to `TransferFunction` system, without copying.

        Returns
        -------
        sys: ZerosPolesGain
            The `TransferFunction` system. If the class is already an instance
            of `TransferFunction` then this instance is returned.
        """
        if isinstance(self, TransferFunction):
            return self
        else:
            return self.to_tf()


class lti(LinearTimeInvariant):
    r"""
    Continuous-time linear time invariant system base class.

    Parameters
    ----------
    *system : arguments
        The `lti` class can be instantiated with either 2, 3 or 4 arguments.
        The following gives the number of arguments and the corresponding
        continuous-time subclass that is created:

            * 2: `TransferFunction`:  (numerator, denominator)
            * 3: `ZerosPolesGain`: (zeros, poles, gain)
            * 4: `StateSpace`:  (A, B, C, D)

        Each argument can be an array or a sequence.

    See Also
    --------
    scipy.signal.lti
    ZerosPolesGain, StateSpace, TransferFunction, dlti

    Notes
    -----
    `lti` instances do not exist directly. Instead, `lti` creates an instance
    of one of its subclasses: `StateSpace`, `TransferFunction` or
    `ZerosPolesGain`.

    If (numerator, denominator) is passed in for ``*system``, coefficients for
    both the numerator and denominator should be specified in descending
    exponent order (e.g., ``s^2 + 3s + 5`` would be represented as ``[1, 3,
    5]``).

    Changing the value of properties that are not directly part of the current
    system representation (such as the `zeros` of a `StateSpace` system) is
    very inefficient and may lead to numerical inaccuracies. It is better to
    convert to the specific system representation first. For example, call
    ``sys = sys.to_zpk()`` before accessing/changing the zeros, poles or gain.
    """
    def __new__(cls, *system):
        """Create an instance of the appropriate subclass."""
        if cls is lti:
            N = len(system)
            if N == 2:
                return TransferFunctionContinuous.__new__(
                    TransferFunctionContinuous, *system)
            elif N == 3:
                return ZerosPolesGainContinuous.__new__(
                    ZerosPolesGainContinuous, *system)
            elif N == 4:
                return StateSpaceContinuous.__new__(StateSpaceContinuous,
                                                    *system)
            else:
                raise ValueError("`system` needs to be an instance of `lti` "
                                 "or have 2, 3 or 4 arguments.")
        # __new__ was called from a subclass, let it call its own functions
        return super().__new__(cls)

    def __init__(self, *system):
        """
        Initialize the `lti` baseclass.

        The heavy lifting is done by the subclasses.
        """
        super().__init__(*system)

    def impulse(self, X0=None, T=None, N=None):
        """
        Return the impulse response of a continuous-time system.
        See `impulse` for details.
        """
        return impulse(self, X0=X0, T=T, N=N)

    def step(self, X0=None, T=None, N=None):
        """
        Return the step response of a continuous-time system.
        See `step` for details.
        """
        return step(self, X0=X0, T=T, N=N)

    def output(self, U, T, X0=None):
        """
        Return the response of a continuous-time system to input `U`.
        See `lsim` for details.
        """
        return lsim(self, U, T, X0=X0)

    def bode(self, w=None, n=100):
        """
        Calculate Bode magnitude and phase data of a continuous-time system.

        Returns a 3-tuple containing arrays of frequencies [rad/s], magnitude
        [dB] and phase [deg]. See `bode` for details.
        """
        return bode(self, w=w, n=n)

    def freqresp(self, w=None, n=10000):
        """
        Calculate the frequency response of a continuous-time system.

        Returns a 2-tuple containing arrays of frequencies [rad/s] and
        complex magnitude.
        See `freqresp` for details.
        """
        return freqresp(self, w=w, n=n)

    def to_discrete(self, dt, method='zoh', alpha=None):
        """Return a discretized version of the current system.

        Parameters: See `cont2discrete` for details.

        Returns
        -------
        sys: instance of `dlti`
        """
        raise NotImplementedError('to_discrete is not implemented for this '
                                  'system class.')


class dlti(LinearTimeInvariant):
    r"""
    Discrete-time linear time invariant system base class.

    Parameters
    ----------
    *system: arguments
        The `dlti` class can be instantiated with either 2, 3 or 4 arguments.
        The following gives the number of arguments and the corresponding
        discrete-time subclass that is created:

            * 2: `TransferFunction`:  (numerator, denominator)
            * 3: `ZerosPolesGain`: (zeros, poles, gain)
            * 4: `StateSpace`:  (A, B, C, D)

        Each argument can be an array or a sequence.
    dt: float, optional
        Sampling time [s] of the discrete-time systems. Defaults to ``True``
        (unspecified sampling time). Must be specified as a keyword argument,
        for example, ``dt=0.1``.

    See Also
    --------
    scipy.signal.dlti
    ZerosPolesGain, StateSpace, TransferFunction, lti

    Notes
    -----
    `dlti` instances do not exist directly. Instead, `dlti` creates an instance
    of one of its subclasses: `StateSpace`, `TransferFunction` or
    `ZerosPolesGain`.

    Changing the value of properties that are not directly part of the current
    system representation (such as the `zeros` of a `StateSpace` system) is
    very inefficient and may lead to numerical inaccuracies.  It is better to
    convert to the specific system representation first. For example, call
    ``sys = sys.to_zpk()`` before accessing/changing the zeros, poles or gain.

    If (numerator, denominator) is passed in for ``*system``, coefficients for
    both the numerator and denominator should be specified in descending
    exponent order (e.g., ``z^2 + 3z + 5`` would be represented as ``[1, 3,
    5]``).
    """
    def __new__(cls, *system, **kwargs):
        """Create an instance of the appropriate subclass."""
        if cls is dlti:
            N = len(system)
            if N == 2:
                return TransferFunctionDiscrete.__new__(
                    TransferFunctionDiscrete, *system, **kwargs)
            elif N == 3:
                return ZerosPolesGainDiscrete.__new__(ZerosPolesGainDiscrete,
                                                      *system, **kwargs)
            elif N == 4:
                return StateSpaceDiscrete.__new__(StateSpaceDiscrete, *system,
                                                  **kwargs)
            else:
                raise ValueError("`system` needs to be an instance of `dlti` "
                                 "or have 2, 3 or 4 arguments.")
        # __new__ was called from a subclass, let it call its own functions
        return super().__new__(cls)

    def __init__(self, *system, **kwargs):
        """
        Initialize the `lti` baseclass.

        The heavy lifting is done by the subclasses.
        """
        dt = kwargs.pop('dt', True)
        super().__init__(*system, **kwargs)

        self.dt = dt

    @property
    def dt(self):
        """Return the sampling time of the system."""
        return self._dt

    @dt.setter
    def dt(self, dt):
        self._dt = dt

    def impulse(self, x0=None, t=None, n=None):
        """
        Return the impulse response of the discrete-time `dlti` system.
        See `dimpulse` for details.
        """
        return dimpulse(self, x0=x0, t=t, n=n)

    def step(self, x0=None, t=None, n=None):
        """
        Return the step response of the discrete-time `dlti` system.
        See `dstep` for details.
        """
        return dstep(self, x0=x0, t=t, n=n)

    def output(self, u, t, x0=None):
        """
        Return the response of the discrete-time system to input `u`.
        See `dlsim` for details.
        """
        return dlsim(self, u, t, x0=x0)

    def bode(self, w=None, n=100):
        r"""
        Calculate Bode magnitude and phase data of a discrete-time system.

        Returns a 3-tuple containing arrays of frequencies [rad/s], magnitude
        [dB] and phase [deg]. See `dbode` for details.
        """
        return dbode(self, w=w, n=n)

    def freqresp(self, w=None, n=10000, whole=False):
        """
        Calculate the frequency response of a discrete-time system.

        Returns a 2-tuple containing arrays of frequencies [rad/s] and
        complex magnitude.
        See `dfreqresp` for details.

        """
        return dfreqresp(self, w=w, n=n, whole=whole)


class TransferFunction(LinearTimeInvariant):
    r"""Linear Time Invariant system class in transfer function form.

    Represents the system as the continuous-time transfer function
    :math:`H(s)=\sum_{i=0}^N b[N-i] s^i / \sum_{j=0}^M a[M-j] s^j` or the
    discrete-time transfer function
    :math:`H(z)=\sum_{i=0}^N b[N-i] z^i / \sum_{j=0}^M a[M-j] z^j`, where
    :math:`b` are elements of the numerator `num`, :math:`a` are elements of
    the denominator `den`, and ``N == len(b) - 1``, ``M == len(a) - 1``.
    `TransferFunction` systems inherit additional
    functionality from the `lti`, respectively the `dlti` classes, depending on
    which system representation is used.

    Parameters
    ----------
    *system: arguments
        The `TransferFunction` class can be instantiated with 1 or 2
        arguments. The following gives the number of input arguments and their
        interpretation:

            * 1: `lti` or `dlti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 2: array_like: (numerator, denominator)
    dt: float, optional
        Sampling time [s] of the discrete-time systems. Defaults to `None`
        (continuous-time). Must be specified as a keyword argument, for
        example, ``dt=0.1``.

    See Also
    --------
    scipy.signal.TransferFunction
    ZerosPolesGain, StateSpace, lti, dlti
    tf2ss, tf2zpk, tf2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `TransferFunction` system representation (such as the `A`, `B`, `C`, `D`
    state-space matrices) is very inefficient and may lead to numerical
    inaccuracies.  It is better to convert to the specific system
    representation first. For example, call ``sys = sys.to_ss()`` before
    accessing/changing the A, B, C, D system matrices.

    If (numerator, denominator) is passed in for ``*system``, coefficients
    for both the numerator and denominator should be specified in descending
    exponent order (e.g. ``s^2 + 3s + 5`` or ``z^2 + 3z + 5`` would be
    represented as ``[1, 3, 5]``)
    """
    def __new__(cls, *system, **kwargs):
        """Handle object conversion if input is an instance of lti."""
        if len(system) == 1 and isinstance(system[0], LinearTimeInvariant):
            return system[0].to_tf()

        # Choose whether to inherit from `lti` or from `dlti`
        if cls is TransferFunction:
            if kwargs.get('dt') is None:
                return TransferFunctionContinuous.__new__(
                    TransferFunctionContinuous,
                    *system,
                    **kwargs)
            else:
                return TransferFunctionDiscrete.__new__(
                    TransferFunctionDiscrete,
                    *system,
                    **kwargs)

        # No special conversion needed
        return super().__new__(cls)

    def __init__(self, *system, **kwargs):
        """Initialize the state space LTI system."""
        # Conversion of lti instances is handled in __new__
        if isinstance(system[0], LinearTimeInvariant):
            return

        # Remove system arguments, not needed by parents anymore
        super().__init__(**kwargs)

        self._num = None
        self._den = None

        self.num, self.den = normalize(*system)

    def __repr__(self):
        """Return representation of the system's transfer function"""
        return '{}(\n{},\n{},\ndt: {}\n)'.format(
            self.__class__.__name__,
            repr(self.num),
            repr(self.den),
            repr(self.dt),
        )

    @property
    def num(self):
        """Numerator of the `TransferFunction` system."""
        return self._num

    @num.setter
    def num(self, num):
        self._num = cupy.atleast_1d(num)

        # Update dimensions
        if len(self.num.shape) > 1:
            self.outputs, self.inputs = self.num.shape
        else:
            self.outputs = 1
            self.inputs = 1

    @property
    def den(self):
        """Denominator of the `TransferFunction` system."""
        return self._den

    @den.setter
    def den(self, den):
        self._den = cupy.atleast_1d(den)

    def _copy(self, system):
        """
        Copy the parameters of another `TransferFunction` object

        Parameters
        ----------
        system : `TransferFunction`
            The `StateSpace` system that is to be copied

        """
        self.num = system.num
        self.den = system.den

    def to_tf(self):
        """
        Return a copy of the current `TransferFunction` system.

        Returns
        -------
        sys : instance of `TransferFunction`
            The current system (copy)

        """
        return copy.deepcopy(self)

    def to_zpk(self):
        """
        Convert system representation to `ZerosPolesGain`.

        Returns
        -------
        sys : instance of `ZerosPolesGain`
            Zeros, poles, gain representation of the current system

        """
        return ZerosPolesGain(*tf2zpk(self.num, self.den),
                              **self._dt_dict)

    def to_ss(self):
        """
        Convert system representation to `StateSpace`.

        Returns
        -------
        sys : instance of `StateSpace`
            State space model of the current system

        """
        return StateSpace(*tf2ss(self.num, self.den),
                          **self._dt_dict)

    @staticmethod
    def _z_to_zinv(num, den):
        """Change a transfer function from the variable `z` to `z**-1`.

        Parameters
        ----------
        num, den: 1d array_like
            Sequences representing the coefficients of the numerator and
            denominator polynomials, in order of descending degree of 'z'.
            That is, ``5z**2 + 3z + 2`` is presented as ``[5, 3, 2]``.

        Returns
        -------
        num, den: 1d array_like
            Sequences representing the coefficients of the numerator and
            denominator polynomials, in order of ascending degree of 'z**-1'.
            That is, ``5 + 3 z**-1 + 2 z**-2`` is presented as ``[5, 3, 2]``.
        """
        diff = len(num) - len(den)
        if diff > 0:
            den = cupy.hstack((cupy.zeros(diff), den))
        elif diff < 0:
            num = cupy.hstack((cupy.zeros(-diff), num))
        return num, den

    @staticmethod
    def _zinv_to_z(num, den):
        """Change a transfer function from the variable `z` to `z**-1`.

        Parameters
        ----------
        num, den: 1d array_like
            Sequences representing the coefficients of the numerator and
            denominator polynomials, in order of ascending degree of 'z**-1'.
            That is, ``5 + 3 z**-1 + 2 z**-2`` is presented as ``[5, 3, 2]``.

        Returns
        -------
        num, den: 1d array_like
            Sequences representing the coefficients of the numerator and
            denominator polynomials, in order of descending degree of 'z'.
            That is, ``5z**2 + 3z + 2`` is presented as ``[5, 3, 2]``.
        """
        diff = len(num) - len(den)
        if diff > 0:
            den = cupy.hstack((den, cupy.zeros(diff)))
        elif diff < 0:
            num = cupy.hstack((num, cupy.zeros(-diff)))
        return num, den


class TransferFunctionContinuous(TransferFunction, lti):
    r"""
    Continuous-time Linear Time Invariant system in transfer function form.

    Represents the system as the transfer function
    :math:`H(s)=\sum_{i=0}^N b[N-i] s^i / \sum_{j=0}^M a[M-j] s^j`, where
    :math:`b` are elements of the numerator `num`, :math:`a` are elements of
    the denominator `den`, and ``N == len(b) - 1``, ``M == len(a) - 1``.
    Continuous-time `TransferFunction` systems inherit additional
    functionality from the `lti` class.

    Parameters
    ----------
    *system: arguments
        The `TransferFunction` class can be instantiated with 1 or 2
        arguments. The following gives the number of input arguments and their
        interpretation:

            * 1: `lti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 2: array_like: (numerator, denominator)

    See Also
    --------
    scipy.signal.TransferFunction
    ZerosPolesGain, StateSpace, lti
    tf2ss, tf2zpk, tf2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `TransferFunction` system representation (such as the `A`, `B`, `C`, `D`
    state-space matrices) is very inefficient and may lead to numerical
    inaccuracies.  It is better to convert to the specific system
    representation first. For example, call ``sys = sys.to_ss()`` before
    accessing/changing the A, B, C, D system matrices.

    If (numerator, denominator) is passed in for ``*system``, coefficients
    for both the numerator and denominator should be specified in descending
    exponent order (e.g. ``s^2 + 3s + 5`` would be represented as
    ``[1, 3, 5]``)

    """

    def to_discrete(self, dt, method='zoh', alpha=None):
        """
        Returns the discretized `TransferFunction` system.

        Parameters: See `cont2discrete` for details.

        Returns
        -------
        sys: instance of `dlti` and `StateSpace`
        """
        return TransferFunction(*cont2discrete((self.num, self.den),
                                               dt,
                                               method=method,
                                               alpha=alpha)[:-1],
                                dt=dt)


class TransferFunctionDiscrete(TransferFunction, dlti):
    r"""
    Discrete-time Linear Time Invariant system in transfer function form.

    Represents the system as the transfer function
    :math:`H(z)=\sum_{i=0}^N b[N-i] z^i / \sum_{j=0}^M a[M-j] z^j`, where
    :math:`b` are elements of the numerator `num`, :math:`a` are elements of
    the denominator `den`, and ``N == len(b) - 1``, ``M == len(a) - 1``.
    Discrete-time `TransferFunction` systems inherit additional functionality
    from the `dlti` class.

    Parameters
    ----------
    *system: arguments
        The `TransferFunction` class can be instantiated with 1 or 2
        arguments. The following gives the number of input arguments and their
        interpretation:

            * 1: `dlti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 2: array_like: (numerator, denominator)
    dt: float, optional
        Sampling time [s] of the discrete-time systems. Defaults to `True`
        (unspecified sampling time). Must be specified as a keyword argument,
        for example, ``dt=0.1``.

    See Also
    --------
    scipy.signal.TransferFunctionDiscrete
    ZerosPolesGain, StateSpace, dlti
    tf2ss, tf2zpk, tf2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `TransferFunction` system representation (such as the `A`, `B`, `C`, `D`
    state-space matrices) is very inefficient and may lead to numerical
    inaccuracies.

    If (numerator, denominator) is passed in for ``*system``, coefficients
    for both the numerator and denominator should be specified in descending
    exponent order (e.g., ``z^2 + 3z + 5`` would be represented as
    ``[1, 3, 5]``).
    """
    pass


class ZerosPolesGain(LinearTimeInvariant):
    r"""
    Linear Time Invariant system class in zeros, poles, gain form.

    Represents the system as the continuous- or discrete-time transfer function
    :math:`H(s)=k \prod_i (s - z[i]) / \prod_j (s - p[j])`, where :math:`k` is
    the `gain`, :math:`z` are the `zeros` and :math:`p` are the `poles`.
    `ZerosPolesGain` systems inherit additional functionality from the `lti`,
    respectively the `dlti` classes, depending on which system representation
    is used.

    Parameters
    ----------
    *system : arguments
        The `ZerosPolesGain` class can be instantiated with 1 or 3
        arguments. The following gives the number of input arguments and their
        interpretation:

            * 1: `lti` or `dlti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 3: array_like: (zeros, poles, gain)
    dt: float, optional
        Sampling time [s] of the discrete-time systems. Defaults to `None`
        (continuous-time). Must be specified as a keyword argument, for
        example, ``dt=0.1``.


    See Also
    --------
    scipy.signal.ZerosPolesGain
    TransferFunction, StateSpace, lti, dlti
    zpk2ss, zpk2tf, zpk2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `ZerosPolesGain` system representation (such as the `A`, `B`, `C`, `D`
    state-space matrices) is very inefficient and may lead to numerical
    inaccuracies.  It is better to convert to the specific system
    representation first. For example, call ``sys = sys.to_ss()`` before
    accessing/changing the A, B, C, D system matrices.
    """
    def __new__(cls, *system, **kwargs):
        """Handle object conversion if input is an instance of `lti`"""
        if len(system) == 1 and isinstance(system[0], LinearTimeInvariant):
            return system[0].to_zpk()

        # Choose whether to inherit from `lti` or from `dlti`
        if cls is ZerosPolesGain:
            if kwargs.get('dt') is None:
                return ZerosPolesGainContinuous.__new__(
                    ZerosPolesGainContinuous,
                    *system,
                    **kwargs)
            else:
                return ZerosPolesGainDiscrete.__new__(
                    ZerosPolesGainDiscrete,
                    *system,
                    **kwargs
                )

        # No special conversion needed
        return super().__new__(cls)

    def __init__(self, *system, **kwargs):
        """Initialize the zeros, poles, gain system."""
        # Conversion of lti instances is handled in __new__
        if isinstance(system[0], LinearTimeInvariant):
            return

        super().__init__(**kwargs)

        self._zeros = None
        self._poles = None
        self._gain = None

        self.zeros, self.poles, self.gain = system

    def __repr__(self):
        """Return representation of the `ZerosPolesGain` system."""
        return '{}(\n{},\n{},\n{},\ndt: {}\n)'.format(
            self.__class__.__name__,
            repr(self.zeros),
            repr(self.poles),
            repr(self.gain),
            repr(self.dt),
        )

    @property
    def zeros(self):
        """Zeros of the `ZerosPolesGain` system."""
        return self._zeros

    @zeros.setter
    def zeros(self, zeros):
        self._zeros = cupy.atleast_1d(zeros)

        # Update dimensions
        if len(self.zeros.shape) > 1:
            self.outputs, self.inputs = self.zeros.shape
        else:
            self.outputs = 1
            self.inputs = 1

    @property
    def poles(self):
        """Poles of the `ZerosPolesGain` system."""
        return self._poles

    @poles.setter
    def poles(self, poles):
        self._poles = cupy.atleast_1d(poles)

    @property
    def gain(self):
        """Gain of the `ZerosPolesGain` system."""
        return self._gain

    @gain.setter
    def gain(self, gain):
        self._gain = gain

    def _copy(self, system):
        """
        Copy the parameters of another `ZerosPolesGain` system.

        Parameters
        ----------
        system : instance of `ZerosPolesGain`
            The zeros, poles gain system that is to be copied

        """
        self.poles = system.poles
        self.zeros = system.zeros
        self.gain = system.gain

    def to_tf(self):
        """
        Convert system representation to `TransferFunction`.

        Returns
        -------
        sys : instance of `TransferFunction`
            Transfer function of the current system

        """
        return TransferFunction(*zpk2tf(self.zeros, self.poles, self.gain),
                                **self._dt_dict)

    def to_zpk(self):
        """
        Return a copy of the current 'ZerosPolesGain' system.

        Returns
        -------
        sys : instance of `ZerosPolesGain`
            The current system (copy)

        """
        return copy.deepcopy(self)

    def to_ss(self):
        """
        Convert system representation to `StateSpace`.

        Returns
        -------
        sys : instance of `StateSpace`
            State space model of the current system

        """
        return StateSpace(*zpk2ss(self.zeros, self.poles, self.gain),
                          **self._dt_dict)


class ZerosPolesGainContinuous(ZerosPolesGain, lti):
    r"""
    Continuous-time Linear Time Invariant system in zeros, poles, gain form.

    Represents the system as the continuous time transfer function
    :math:`H(s)=k \prod_i (s - z[i]) / \prod_j (s - p[j])`, where :math:`k` is
    the `gain`, :math:`z` are the `zeros` and :math:`p` are the `poles`.
    Continuous-time `ZerosPolesGain` systems inherit additional functionality
    from the `lti` class.

    Parameters
    ----------
    *system : arguments
        The `ZerosPolesGain` class can be instantiated with 1 or 3
        arguments. The following gives the number of input arguments and their
        interpretation:

            * 1: `lti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 3: array_like: (zeros, poles, gain)

    See Also
    --------
    TransferFunction, StateSpace, lti
    zpk2ss, zpk2tf, zpk2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `ZerosPolesGain` system representation (such as the `A`, `B`, `C`, `D`
    state-space matrices) is very inefficient and may lead to numerical
    inaccuracies.  It is better to convert to the specific system
    representation first. For example, call ``sys = sys.to_ss()`` before
    accessing/changing the A, B, C, D system matrices.

    Examples
    --------
    Construct the transfer function
    :math:`H(s)=\frac{5(s - 1)(s - 2)}{(s - 3)(s - 4)}`:

    >>> from scipy import signal

    >>> signal.ZerosPolesGain([1, 2], [3, 4], 5)
    ZerosPolesGainContinuous(
    array([1, 2]),
    array([3, 4]),
    5,
    dt: None
    )

    """

    def to_discrete(self, dt, method='zoh', alpha=None):
        """
        Returns the discretized `ZerosPolesGain` system.

        Parameters: See `cont2discrete` for details.

        Returns
        -------
        sys: instance of `dlti` and `ZerosPolesGain`
        """
        return ZerosPolesGain(
            *cont2discrete((self.zeros, self.poles, self.gain),
                           dt,
                           method=method,
                           alpha=alpha)[:-1],
            dt=dt)


class ZerosPolesGainDiscrete(ZerosPolesGain, dlti):
    r"""
    Discrete-time Linear Time Invariant system in zeros, poles, gain form.

    Represents the system as the discrete-time transfer function
    :math:`H(z)=k \prod_i (z - q[i]) / \prod_j (z - p[j])`, where :math:`k` is
    the `gain`, :math:`q` are the `zeros` and :math:`p` are the `poles`.
    Discrete-time `ZerosPolesGain` systems inherit additional functionality
    from the `dlti` class.

    Parameters
    ----------
    *system : arguments
        The `ZerosPolesGain` class can be instantiated with 1 or 3
        arguments. The following gives the number of input arguments and their
        interpretation:

            * 1: `dlti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 3: array_like: (zeros, poles, gain)
    dt: float, optional
        Sampling time [s] of the discrete-time systems. Defaults to `True`
        (unspecified sampling time). Must be specified as a keyword argument,
        for example, ``dt=0.1``.

    See Also
    --------
    scipy.signal.ZerosPolesGainDiscrete
    TransferFunction, StateSpace, dlti
    zpk2ss, zpk2tf, zpk2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `ZerosPolesGain` system representation (such as the `A`, `B`, `C`, `D`
    state-space matrices) is very inefficient and may lead to numerical
    inaccuracies.  It is better to convert to the specific system
    representation first. For example, call ``sys = sys.to_ss()`` before
    accessing/changing the A, B, C, D system matrices.
    """
    pass


class StateSpace(LinearTimeInvariant):
    r"""
    Linear Time Invariant system in state-space form.

    Represents the system as the continuous-time, first order differential
    equation :math:`\dot{x} = A x + B u` or the discrete-time difference
    equation :math:`x[k+1] = A x[k] + B u[k]`. `StateSpace` systems
    inherit additional functionality from the `lti`, respectively the `dlti`
    classes, depending on which system representation is used.

    Parameters
    ----------
    *system: arguments
        The `StateSpace` class can be instantiated with 1 or 4 arguments.
        The following gives the number of input arguments and their
        interpretation:

            * 1: `lti` or `dlti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 4: array_like: (A, B, C, D)
    dt: float, optional
        Sampling time [s] of the discrete-time systems. Defaults to `None`
        (continuous-time). Must be specified as a keyword argument, for
        example, ``dt=0.1``.

    See Also
    --------
    scipy.signal.StateSpace
    TransferFunction, ZerosPolesGain, lti, dlti
    ss2zpk, ss2tf, zpk2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `StateSpace` system representation (such as `zeros` or `poles`) is very
    inefficient and may lead to numerical inaccuracies.  It is better to
    convert to the specific system representation first. For example, call
    ``sys = sys.to_zpk()`` before accessing/changing the zeros, poles or gain.
    """

    # Override NumPy binary operations and ufuncs
    __array_priority__ = 100.0
    __array_ufunc__ = None

    def __new__(cls, *system, **kwargs):
        """Create new StateSpace object and settle inheritance."""
        # Handle object conversion if input is an instance of `lti`
        if len(system) == 1 and isinstance(system[0], LinearTimeInvariant):
            return system[0].to_ss()

        # Choose whether to inherit from `lti` or from `dlti`
        if cls is StateSpace:
            if kwargs.get('dt') is None:
                return StateSpaceContinuous.__new__(StateSpaceContinuous,
                                                    *system, **kwargs)
            else:
                return StateSpaceDiscrete.__new__(StateSpaceDiscrete,
                                                  *system, **kwargs)

        # No special conversion needed
        return super().__new__(cls)

    def __init__(self, *system, **kwargs):
        """Initialize the state space lti/dlti system."""
        # Conversion of lti instances is handled in __new__
        if isinstance(system[0], LinearTimeInvariant):
            return

        # Remove system arguments, not needed by parents anymore
        super().__init__(**kwargs)

        self._A = None
        self._B = None
        self._C = None
        self._D = None

        self.A, self.B, self.C, self.D = abcd_normalize(*system)

    def __repr__(self):
        """Return representation of the `StateSpace` system."""
        return '{}(\n{},\n{},\n{},\n{},\ndt: {}\n)'.format(
            self.__class__.__name__,
            repr(self.A),
            repr(self.B),
            repr(self.C),
            repr(self.D),
            repr(self.dt),
        )

    def _check_binop_other(self, other):
        return isinstance(other, (StateSpace, cupy.ndarray, float, complex,
                                  cupy.number, int))

    def __mul__(self, other):
        """
        Post-multiply another system or a scalar

        Handles multiplication of systems in the sense of a frequency domain
        multiplication. That means, given two systems E1(s) and E2(s), their
        multiplication, H(s) = E1(s) * E2(s), means that applying H(s) to U(s)
        is equivalent to first applying E2(s), and then E1(s).

        Notes
        -----
        For SISO systems the order of system application does not matter.
        However, for MIMO systems, where the two systems are matrices, the
        order above ensures standard Matrix multiplication rules apply.
        """
        if not self._check_binop_other(other):
            return NotImplemented

        if isinstance(other, StateSpace):
            # Disallow mix of discrete and continuous systems.
            if type(other) is not type(self):
                return NotImplemented

            if self.dt != other.dt:
                raise TypeError('Cannot multiply systems with different `dt`.')

            n1 = self.A.shape[0]
            n2 = other.A.shape[0]

            # Interconnection of systems
            # x1' = A1 x1 + B1 u1
            # y1  = C1 x1 + D1 u1
            # x2' = A2 x2 + B2 y1
            # y2  = C2 x2 + D2 y1
            #
            # Plugging in with u1 = y2 yields
            # [x1']   [A1 B1*C2 ] [x1]   [B1*D2]
            # [x2'] = [0  A2    ] [x2] + [B2   ] u2
            #                    [x1]
            #  y2   = [C1 D1*C2] [x2] + D1*D2 u2
            a = cupy.vstack((cupy.hstack((self.A, self.B @ other.C)),
                             cupy.hstack((cupy.zeros((n2, n1)), other.A))))
            b = cupy.vstack((self.B @ other.D, other.B))
            c = cupy.hstack((self.C, self.D @ other.C))
            d = self.D @ other.D
        else:
            # Assume that other is a scalar / matrix
            # For post multiplication the input gets scaled
            a = self.A
            b = self.B @ other
            c = self.C
            d = self.D @ other

        common_dtype = cupy.result_type(a.dtype, b.dtype, c.dtype, d.dtype)
        return StateSpace(cupy.asarray(a, dtype=common_dtype),
                          cupy.asarray(b, dtype=common_dtype),
                          cupy.asarray(c, dtype=common_dtype),
                          cupy.asarray(d, dtype=common_dtype),
                          **self._dt_dict)

    def __rmul__(self, other):
        """Pre-multiply a scalar or matrix (but not StateSpace)"""
        if not self._check_binop_other(other) or isinstance(other, StateSpace):
            return NotImplemented

        # For pre-multiplication only the output gets scaled
        a = self.A
        b = self.B
        c = other @ self.C
        d = other @ self.D

        common_dtype = cupy.result_type(a.dtype, b.dtype, c.dtype, d.dtype)
        return StateSpace(cupy.asarray(a, dtype=common_dtype),
                          cupy.asarray(b, dtype=common_dtype),
                          cupy.asarray(c, dtype=common_dtype),
                          cupy.asarray(d, dtype=common_dtype),
                          **self._dt_dict)

    def __neg__(self):
        """Negate the system (equivalent to pre-multiplying by -1)."""
        return StateSpace(self.A, self.B, -self.C, -self.D, **self._dt_dict)

    def __add__(self, other):
        """
        Adds two systems in the sense of frequency domain addition.
        """
        if not self._check_binop_other(other):
            return NotImplemented

        if isinstance(other, StateSpace):
            # Disallow mix of discrete and continuous systems.
            if type(other) is not type(self):
                raise TypeError('Cannot add {} and {}'.format(type(self),
                                                              type(other)))

            if self.dt != other.dt:
                raise TypeError('Cannot add systems with different `dt`.')
            # Interconnection of systems
            # x1' = A1 x1 + B1 u
            # y1  = C1 x1 + D1 u
            # x2' = A2 x2 + B2 u
            # y2  = C2 x2 + D2 u
            # y   = y1 + y2
            #
            # Plugging in yields
            # [x1']   [A1 0 ] [x1]   [B1]
            # [x2'] = [0  A2] [x2] + [B2] u
            #                 [x1]
            #  y    = [C1 C2] [x2] + [D1 + D2] u
            a = linalg.block_diag(self.A, other.A)
            b = cupy.vstack((self.B, other.B))
            c = cupy.hstack((self.C, other.C))
            d = self.D + other.D
        else:
            other = cupy.atleast_2d(other)
            if self.D.shape == other.shape:
                # A scalar/matrix is really just a static system
                # (A=0, B=0, C=0)
                a = self.A
                b = self.B
                c = self.C
                d = self.D + other
            else:
                raise ValueError("Cannot add systems with incompatible "
                                 "dimensions ({} and {})"
                                 .format(self.D.shape, other.shape))

        common_dtype = cupy.result_type(a.dtype, b.dtype, c.dtype, d.dtype)
        return StateSpace(cupy.asarray(a, dtype=common_dtype),
                          cupy.asarray(b, dtype=common_dtype),
                          cupy.asarray(c, dtype=common_dtype),
                          cupy.asarray(d, dtype=common_dtype),
                          **self._dt_dict)

    def __sub__(self, other):
        if not self._check_binop_other(other):
            return NotImplemented

        return self.__add__(-other)

    def __radd__(self, other):
        if not self._check_binop_other(other):
            return NotImplemented

        return self.__add__(other)

    def __rsub__(self, other):
        if not self._check_binop_other(other):
            return NotImplemented

        return (-self).__add__(other)

    def __truediv__(self, other):
        """
        Divide by a scalar
        """
        # Division by non-StateSpace scalars
        if not self._check_binop_other(other) or isinstance(other, StateSpace):
            return NotImplemented

        if isinstance(other, cupy.ndarray) and other.ndim > 0:
            # It's ambiguous what this means, so disallow it
            raise ValueError(
                "Cannot divide StateSpace by non-scalar numpy arrays")

        return self.__mul__(1/other)

    @property
    def A(self):
        """State matrix of the `StateSpace` system."""
        return self._A

    @A.setter
    def A(self, A):
        self._A = _atleast_2d_or_none(A)

    @property
    def B(self):
        """Input matrix of the `StateSpace` system."""
        return self._B

    @B.setter
    def B(self, B):
        self._B = _atleast_2d_or_none(B)
        self.inputs = self.B.shape[-1]

    @property
    def C(self):
        """Output matrix of the `StateSpace` system."""
        return self._C

    @C.setter
    def C(self, C):
        self._C = _atleast_2d_or_none(C)
        self.outputs = self.C.shape[0]

    @property
    def D(self):
        """Feedthrough matrix of the `StateSpace` system."""
        return self._D

    @D.setter
    def D(self, D):
        self._D = _atleast_2d_or_none(D)

    def _copy(self, system):
        """
        Copy the parameters of another `StateSpace` system.

        Parameters
        ----------
        system : instance of `StateSpace`
            The state-space system that is to be copied

        """
        self.A = system.A
        self.B = system.B
        self.C = system.C
        self.D = system.D

    def to_tf(self, **kwargs):
        """
        Convert system representation to `TransferFunction`.

        Parameters
        ----------
        kwargs : dict, optional
            Additional keywords passed to `ss2zpk`

        Returns
        -------
        sys : instance of `TransferFunction`
            Transfer function of the current system

        """
        return TransferFunction(*ss2tf(self._A, self._B, self._C, self._D,
                                       **kwargs), **self._dt_dict)

    def to_zpk(self, **kwargs):
        """
        Convert system representation to `ZerosPolesGain`.

        Parameters
        ----------
        kwargs : dict, optional
            Additional keywords passed to `ss2zpk`

        Returns
        -------
        sys : instance of `ZerosPolesGain`
            Zeros, poles, gain representation of the current system

        """
        return ZerosPolesGain(*ss2zpk(self._A, self._B, self._C, self._D,
                                      **kwargs), **self._dt_dict)

    def to_ss(self):
        """
        Return a copy of the current `StateSpace` system.

        Returns
        -------
        sys : instance of `StateSpace`
            The current system (copy)

        """
        return copy.deepcopy(self)


class StateSpaceContinuous(StateSpace, lti):
    r"""
    Continuous-time Linear Time Invariant system in state-space form.

    Represents the system as the continuous-time, first order differential
    equation :math:`\dot{x} = A x + B u`.
    Continuous-time `StateSpace` systems inherit additional functionality
    from the `lti` class.

    Parameters
    ----------
    *system: arguments
        The `StateSpace` class can be instantiated with 1 or 3 arguments.
        The following gives the number of input arguments and their
        interpretation:

            * 1: `lti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 4: array_like: (A, B, C, D)

    See Also
    --------
    scipy.signal.StateSpaceContinuous
    TransferFunction, ZerosPolesGain, lti
    ss2zpk, ss2tf, zpk2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `StateSpace` system representation (such as `zeros` or `poles`) is very
    inefficient and may lead to numerical inaccuracies.  It is better to
    convert to the specific system representation first. For example, call
    ``sys = sys.to_zpk()`` before accessing/changing the zeros, poles or gain.
    """

    def to_discrete(self, dt, method='zoh', alpha=None):
        """
        Returns the discretized `StateSpace` system.

        Parameters: See `cont2discrete` for details.

        Returns
        -------
        sys: instance of `dlti` and `StateSpace`
        """
        return StateSpace(*cont2discrete((self.A, self.B, self.C, self.D),
                                         dt,
                                         method=method,
                                         alpha=alpha)[:-1],
                          dt=dt)


class StateSpaceDiscrete(StateSpace, dlti):
    r"""
    Discrete-time Linear Time Invariant system in state-space form.

    Represents the system as the discrete-time difference equation
    :math:`x[k+1] = A x[k] + B u[k]`.
    `StateSpace` systems inherit additional functionality from the `dlti`
    class.

    Parameters
    ----------
    *system: arguments
        The `StateSpace` class can be instantiated with 1 or 3 arguments.
        The following gives the number of input arguments and their
        interpretation:

            * 1: `dlti` system: (`StateSpace`, `TransferFunction` or
              `ZerosPolesGain`)
            * 4: array_like: (A, B, C, D)
    dt: float, optional
        Sampling time [s] of the discrete-time systems. Defaults to `True`
        (unspecified sampling time). Must be specified as a keyword argument,
        for example, ``dt=0.1``.

    See Also
    --------
    scipy.signal.StateSpaceDiscrete
    TransferFunction, ZerosPolesGain, dlti
    ss2zpk, ss2tf, zpk2sos

    Notes
    -----
    Changing the value of properties that are not part of the
    `StateSpace` system representation (such as `zeros` or `poles`) is very
    inefficient and may lead to numerical inaccuracies.  It is better to
    convert to the specific system representation first. For example, call
    ``sys = sys.to_zpk()`` before accessing/changing the zeros, poles or gain.
    """
    pass


# ### dlsim and related functions ###

def dlsim(system, u, t=None, x0=None):
    """
    Simulate output of a discrete-time linear system.

    Parameters
    ----------
    system : tuple of array_like or instance of `dlti`
        A tuple describing the system.
        The following gives the number of elements in the tuple and
        the interpretation:

            * 1: (instance of `dlti`)
            * 3: (num, den, dt)
            * 4: (zeros, poles, gain, dt)
            * 5: (A, B, C, D, dt)

    u : array_like
        An input array describing the input at each time `t` (interpolation is
        assumed between given times).  If there are multiple inputs, then each
        column of the rank-2 array represents an input.
    t : array_like, optional
        The time steps at which the input is defined.  If `t` is given, it
        must be the same length as `u`, and the final value in `t` determines
        the number of steps returned in the output.
    x0 : array_like, optional
        The initial conditions on the state vector (zero by default).

    Returns
    -------
    tout : ndarray
        Time values for the output, as a 1-D array.
    yout : ndarray
        System response, as a 1-D array.
    xout : ndarray, optional
        Time-evolution of the state-vector.  Only generated if the input is a
        `StateSpace` system.

    See Also
    --------
    scipy.signal.dlsim
    lsim, dstep, dimpulse, cont2discrete
    """
    # Convert system to dlti-StateSpace
    if isinstance(system, lti):
        raise AttributeError('dlsim can only be used with discrete-time dlti '
                             'systems.')
    elif not isinstance(system, dlti):
        system = dlti(*system[:-1], dt=system[-1])

    # Condition needed to ensure output remains compatible
    is_ss_input = isinstance(system, StateSpace)
    system = system._as_ss()

    u = cupy.atleast_1d(u)

    if u.ndim == 1:
        u = cupy.atleast_2d(u).T

    if t is None:
        out_samples = len(u)
        stoptime = (out_samples - 1) * system.dt
    else:
        stoptime = t[-1]
        out_samples = int(cupy.floor(stoptime / system.dt)) + 1

    # Pre-build output arrays
    xout = cupy.zeros((out_samples, system.A.shape[0]))
    yout = cupy.zeros((out_samples, system.C.shape[0]))
    tout = cupy.linspace(0.0, stoptime, num=out_samples)

    # Check initial condition
    if x0 is None:
        xout[0, :] = cupy.zeros((system.A.shape[1],))
    else:
        xout[0, :] = cupy.asarray(x0)

    # Pre-interpolate inputs into the desired time steps
    if t is None:
        u_dt = u
    else:
        if len(u.shape) == 1:
            u = u[:, None]

        u_dt = make_interp_spline(t, u, k=1)(tout)

    # Simulate the system
    for i in range(0, out_samples - 1):
        xout[i+1, :] = system.A @ xout[i, :] + system.B @ u_dt[i, :]
        yout[i, :] = system.C @ xout[i, :] + system.D @ u_dt[i, :]

    # Last point
    yout[out_samples-1, :] = (system.C @ xout[out_samples-1, :] +
                              system.D @ u_dt[out_samples-1, :])

    if is_ss_input:
        return tout, yout, xout
    else:
        return tout, yout


def dimpulse(system, x0=None, t=None, n=None):
    """
    Impulse response of discrete-time system.

    Parameters
    ----------
    system : tuple of array_like or instance of `dlti`
        A tuple describing the system.
        The following gives the number of elements in the tuple and
        the interpretation:

            * 1: (instance of `dlti`)
            * 3: (num, den, dt)
            * 4: (zeros, poles, gain, dt)
            * 5: (A, B, C, D, dt)

    x0 : array_like, optional
        Initial state-vector.  Defaults to zero.
    t : array_like, optional
        Time points.  Computed if not given.
    n : int, optional
        The number of time points to compute (if `t` is not given).

    Returns
    -------
    tout : ndarray
        Time values for the output, as a 1-D array.
    yout : tuple of ndarray
        Impulse response of system.  Each element of the tuple represents
        the output of the system based on an impulse in each input.

    See Also
    --------
    scipy.signal.dimpulse
    impulse, dstep, dlsim, cont2discrete
    """
    # Convert system to dlti-StateSpace
    if isinstance(system, dlti):
        system = system._as_ss()
    elif isinstance(system, lti):
        raise AttributeError('dimpulse can only be used with discrete-time '
                             'dlti systems.')
    else:
        system = dlti(*system[:-1], dt=system[-1])._as_ss()

    # Default to 100 samples if unspecified
    if n is None:
        n = 100

    # If time is not specified, use the number of samples
    # and system dt
    if t is None:
        t = cupy.linspace(0, n * system.dt, n, endpoint=False)
    else:
        t = cupy.asarray(t)

    # For each input, implement a step change
    yout = None
    for i in range(0, system.inputs):
        u = cupy.zeros((t.shape[0], system.inputs))
        u[0, i] = 1.0

        one_output = dlsim(system, u, t=t, x0=x0)

        if yout is None:
            yout = (one_output[1],)
        else:
            yout = yout + (one_output[1],)

        tout = one_output[0]

    return tout, yout


def dstep(system, x0=None, t=None, n=None):
    """
    Step response of discrete-time system.

    Parameters
    ----------
    system : tuple of array_like
        A tuple describing the system.
        The following gives the number of elements in the tuple and
        the interpretation:

            * 1: (instance of `dlti`)
            * 3: (num, den, dt)
            * 4: (zeros, poles, gain, dt)
            * 5: (A, B, C, D, dt)

    x0 : array_like, optional
        Initial state-vector.  Defaults to zero.
    t : array_like, optional
        Time points.  Computed if not given.
    n : int, optional
        The number of time points to compute (if `t` is not given).

    Returns
    -------
    tout : ndarray
        Output time points, as a 1-D array.
    yout : tuple of ndarray
        Step response of system.  Each element of the tuple represents
        the output of the system based on a step response to each input.

    See Also
    --------
    scipy.signal.dlstep
    step, dimpulse, dlsim, cont2discrete
    """
    # Convert system to dlti-StateSpace
    if isinstance(system, dlti):
        system = system._as_ss()
    elif isinstance(system, lti):
        raise AttributeError('dstep can only be used with discrete-time dlti '
                             'systems.')
    else:
        system = dlti(*system[:-1], dt=system[-1])._as_ss()

    # Default to 100 samples if unspecified
    if n is None:
        n = 100

    # If time is not specified, use the number of samples
    # and system dt
    if t is None:
        t = cupy.linspace(0, n * system.dt, n, endpoint=False)
    else:
        t = cupy.asarray(t)

    # For each input, implement a step change
    yout = None
    for i in range(0, system.inputs):
        u = cupy.zeros((t.shape[0], system.inputs))
        u[:, i] = cupy.ones((t.shape[0],))

        one_output = dlsim(system, u, t=t, x0=x0)

        if yout is None:
            yout = (one_output[1],)
        else:
            yout = yout + (one_output[1],)

        tout = one_output[0]

    return tout, yout


def dfreqresp(system, w=None, n=10000, whole=False):
    r"""
    Calculate the frequency response of a discrete-time system.

    Parameters
    ----------
    system : an instance of the `dlti` class or a tuple describing the system.
        The following gives the number of elements in the tuple and
        the interpretation:

            * 1 (instance of `dlti`)
            * 2 (numerator, denominator, dt)
            * 3 (zeros, poles, gain, dt)
            * 4 (A, B, C, D, dt)

    w : array_like, optional
        Array of frequencies (in radians/sample). Magnitude and phase data is
        calculated for every value in this array. If not given a reasonable
        set will be calculated.
    n : int, optional
        Number of frequency points to compute if `w` is not given. The `n`
        frequencies are logarithmically spaced in an interval chosen to
        include the influence of the poles and zeros of the system.
    whole : bool, optional
        Normally, if 'w' is not given, frequencies are computed from 0 to the
        Nyquist frequency, pi radians/sample (upper-half of unit-circle). If
        `whole` is True, compute frequencies from 0 to 2*pi radians/sample.

    Returns
    -------
    w : 1D ndarray
        Frequency array [radians/sample]
    H : 1D ndarray
        Array of complex magnitude values

    See Also
    --------
    scipy.signal.dfeqresp

    Notes
    -----
    If (num, den) is passed in for ``system``, coefficients for both the
    numerator and denominator should be specified in descending exponent
    order (e.g. ``z^2 + 3z + 5`` would be represented as ``[1, 3, 5]``).
    """
    if not isinstance(system, dlti):
        if isinstance(system, lti):
            raise AttributeError('dfreqresp can only be used with '
                                 'discrete-time systems.')

        system = dlti(*system[:-1], dt=system[-1])

    if isinstance(system, StateSpace):
        # No SS->ZPK code exists right now, just SS->TF->ZPK
        system = system._as_tf()

    if not isinstance(system, (TransferFunction, ZerosPolesGain)):
        raise ValueError('Unknown system type')

    if system.inputs != 1 or system.outputs != 1:
        raise ValueError("dfreqresp requires a SISO (single input, single "
                         "output) system.")

    if w is not None:
        worN = w
    else:
        worN = n

    if isinstance(system, TransferFunction):
        # Convert numerator and denominator from polynomials in the variable
        # 'z' to polynomials in the variable 'z^-1', as freqz expects.
        num, den = TransferFunction._z_to_zinv(system.num.ravel(), system.den)
        w, h = freqz(num, den, worN=worN, whole=whole)

    elif isinstance(system, ZerosPolesGain):
        w, h = freqz_zpk(system.zeros, system.poles, system.gain, worN=worN,
                         whole=whole)

    return w, h


def dbode(system, w=None, n=100):
    r"""
    Calculate Bode magnitude and phase data of a discrete-time system.

    Parameters
    ----------
    system : an instance of the LTI class or a tuple describing the system.
        The following gives the number of elements in the tuple and
        the interpretation:

            * 1 (instance of `dlti`)
            * 2 (num, den, dt)
            * 3 (zeros, poles, gain, dt)
            * 4 (A, B, C, D, dt)

    w : array_like, optional
        Array of frequencies (in radians/sample). Magnitude and phase data is
        calculated for every value in this array. If not given a reasonable
        set will be calculated.
    n : int, optional
        Number of frequency points to compute if `w` is not given. The `n`
        frequencies are logarithmically spaced in an interval chosen to
        include the influence of the poles and zeros of the system.

    Returns
    -------
    w : 1D ndarray
        Frequency array [rad/time_unit]
    mag : 1D ndarray
        Magnitude array [dB]
    phase : 1D ndarray
        Phase array [deg]

    See Also
    --------
    scipy.signal.dbode

    Notes
    -----
    If (num, den) is passed in for ``system``, coefficients for both the
    numerator and denominator should be specified in descending exponent
    order (e.g. ``z^2 + 3z + 5`` would be represented as ``[1, 3, 5]``).
    """
    w, y = dfreqresp(system, w=w, n=n)

    if isinstance(system, dlti):
        dt = system.dt
    else:
        dt = system[-1]

    mag = 20.0 * cupy.log10(abs(y))
    phase = cupy.rad2deg(cupy.unwrap(cupy.angle(y)))

    return w / dt, mag, phase
