#!/usr/bin/env python2.7

from __future__ import division
import numpy as np
from numpy import pi
from scipy.integrate import complex_ode

from ep.helpers import c_eig, c_trapz, c_cumtrapz, map_trajectory


class Base:
    """Base class."""

    def __init__(self, T=100, tN=50, x_R0=0.05, y_R0=0.4, loop_type="Circle",
                 loop_direction='-', init_state='a', init_state_method='gain',
                 init_phase=0.0, calc_adiabatic_state=False, verbose=False):
        """Exceptional Point (EP) base class.

        The dynamics of a 2-level system are determined via a Runge-Kutta
        method of order (4) 5 due to Dormand and Prince.

            Parameters:
            -----------
                T : float, optional
                    Total duration of the loop in parameter space.
                tN: int, optional
                    Number of timesteps per unit time in the ODE-integration.
                x_R0 : float, optional
                    x-coordinate of the loop parametrization.
                y_R0 : float, optional
                    y-coordinate of the loop parametrization.
                init_state : str, optional
                    Determines initial state for the system's evolution:
                       'a': populate gain state |a>
                       'b': populate loss state |b>
                       'c': superposition of gain and loss state:
                                2^(-1/2)*(|a> + |b>)
                       'd': superposition of gain and loss state:
                                2^(-1/2)*(|a> - |b>)
                init_state_method: str, optional ('gain'|'energy')
                    Determines which method to use for sorting the eigensystem.
                loop_type : str, optional
                    Loop trajectory shape.
                loop_direction : str, optional ('-'|'+')
                    Direction of evolution around the EP (-: ccw, +: cw).
                init_phase : float, optional
                    Starting point of evolution on trajectory.
                calc_adiabatic_state : bool, optional
                    Whether adiabatic solutions should also be calculated (note
                    that setting this flag True can slow down the computation
                    considerably).
                verbose: bool, optional
                    Whether to return additional output.
        """
        self.T = T

        self.init_state = init_state
        self.init_state_method = init_state_method
        self.loop_type = loop_type
        self.loop_direction = loop_direction

        # number of timesteps in ODE-integration
        self.tN = tN * T

        # time-array and step-size
        self.t, self.dt = np.linspace(0, T, self.tN, retstep=True)

        # loop frequency
        self.w = 2.*pi/T
        if self.loop_direction == '+':
            self.w = -self.w

        # loop cycle parameters
        self.x_R0, self.y_R0 = x_R0, y_R0
        self.init_phase = init_phase

        # wavefunction |Psi(t)>
        self.Psi = np.zeros((self.tN, 2), dtype=np.complex256)

        # instantaneous eigenvalues E_a, E_b and corresponding eigenvectors
        # |phi_a> and |phi_b>
        self.eVals = np.zeros((self.tN, 2), dtype=np.complex256)
        self.eVecs_r = np.zeros((self.tN, 2, 2), dtype=np.complex256)
        self.eVecs_l = np.zeros((self.tN, 2, 2), dtype=np.complex256)

        # adiabatic coefficient and adiabatic phase
        self.Psi_adiabatic = np.zeros((self.tN, 2), dtype=np.complex256)
        self.theta_adiabatic = np.zeros((self.tN, 2), dtype=np.complex256)

        self.calc_adiabatic_state = calc_adiabatic_state
        self.verbose = verbose

    def get_cycle_parameters(self, t):
        """get_cycle_parameters method is overwritten by inheriting classes."""
        pass

    def H(self, t, x=None, y=None):
        """Hamiltonian H is overwritten by inheriting classes."""
        pass

    def sample_H(self, xmin=None, xmax=None, xN=None, ymin=None, ymax=None,
                 yN=None, verbose=False):
        """Sample local eigenvalue geometry of Hamiltonian H.

            Parameters:
            -----------
                xmin, xmax: float
                    Dimensions in x-direction.
                ymin, ymax: float
                    Dimensions in y-direction.
                xN, yN: int
                    Number of sampling points in x and y direction.
                verbose: bool
                    Show additional output.

            Returns:
            --------
                X, Y: (N,N) ndarray
                    Spatial (mesh)grids.
                Z: (N,N,2) ndarray
                    Eigenvalues evaluated on the X/Y grid.
        """

        if xN is None:
            xN = 5*10**2
        if yN is None:
            yN = 5*10**2

        # if xmin is None or xmax is None:
        #     xmin = self.x_EP - 0.15*self.x_R0
        #     xmax = self.x_EP + 0.15*self.x_R0
        #
        # if ymin is None or ymax is None:
        #     ymin = self.y_EP - 0.15*self.y_R0
        #     ymax = self.y_EP + 0.15*self.y_R0

        x = np.linspace(xmin, xmax, xN)
        y = np.linspace(ymin, ymax, yN)

        X, Y = np.meshgrid(x, y, indexing='ij')
        Z = np.zeros((xN, yN, 2), dtype=complex)

        for i, xi in enumerate(x):
            for j, yj in enumerate(y):
                if verbose:
                    print "(i,j) =", i, j
                H = self.H(0, x=xi, y=yj)
                Z[i, j, :] = c_eig(H)[0]

        return X, Y, Z

    def sample_H_eigenvectors(self, xmin=None, xmax=None, xN=None, ymin=None,
                              ymax=None, yN=None, verbose=False):
        """Sample local eigenvectors of Hamiltonian H.

            Parameters:
            -----------
                xmin, xmax: float
                    Dimensions in x-direction.
                ymin, ymax: float
                    Dimensions in y-direction.
                xN, yN: int
                    Number of sampling points in x and y direction.
                verbose: bool
                    Show additional output.

            Returns:
            --------
                X, Y: (N,N) ndarray
                    Spatial (mesh)grids.
                Z: (N,N,2,2) ndarray
                    Eigenvectors evaluated on the X/Y grid.
        """

        if xN is None:
            xN = 5*10**2
        if yN is None:
            yN = 5*10**2

        # if xmin is None or xmax is None:
        #     xmin = self.x_EP - 0.15*self.x_R0
        #     xmax = self.x_EP + 0.15*self.x_R0
        #
        # if ymin is None or ymax is None:
        #     ymin = self.y_EP - 0.15*self.y_R0
        #     ymax = self.y_EP + 0.15*self.y_R0

        x = np.linspace(xmin, xmax, xN)
        y = np.linspace(ymin, ymax, yN)

        X, Y = np.meshgrid(x, y, indexing='ij')
        Z = np.zeros((xN, yN, 2, 2), dtype=complex)

        for i, xi in enumerate(x):
            for j, yj in enumerate(y):
                if verbose:
                    print "(i,j) =", i, j
                H = self.H(0, x=xi, y=yj)
                Z[i, j, :, :] = c_eig(H)[1]

        return X, Y, Z


    def plot_3D_spectrum(self, xmin=None, xmax=None, xN=None, ymin=None,
                         ymax=None, yN=None, trajectory=False, tube_radius=1e-2,
                         part='imag'):
        """Plot the Riemann sheet structure around the EP.

            Parameters:
            -----------
                xmin, xmax: float
                    Dimensions in x-direction.
                ymin, ymax: float
                    Dimensions in y-direction.
                xN, yN: int
                    Number of sampling points in x and y direction.
                trajectory: bool
                    Whether to include a projected trajectory of the eigenbasis
                    coefficients.
                part: str
                    Which function to apply to the eigenvalues before plotting.
                tube_radius: float
                    Trajectory tube thickness.
        """
        from mayavi import mlab

        X, Y, Z = self.sample_H(xmin, xmax, xN, ymin, ymax, yN)
        Z0, Z1 = [Z[..., n] for n in (0, 1)]

        def get_min_and_max(*args):
            data = np.concatenate(*args)
            return data.min(), data.max()

        surf_kwargs = dict(colormap='Spectral', mask=np.diff(Z0.real) > 0.015)

        mlab.figure(0)
        Z_min, Z_max = get_min_and_max([Z0.real, Z1.real])
        mlab.surf(X.real, Y.real, Z0.real, vmin=Z_min, vmax=Z_max, **surf_kwargs)
        mlab.surf(X.real, Y.real, Z1.real, vmin=Z_min, vmax=Z_max, **surf_kwargs)
        mlab.axes(zlabel="Re(E)")

        mlab.figure(1)
        Z_min, Z_max = get_min_and_max([Z0.imag, Z1.imag])
        mlab.mesh(X.real, Y.real, Z0.imag, vmin=Z_min, vmax=Z_max, **surf_kwargs)
        mlab.mesh(X.real, Y.real, Z1.imag, vmin=Z_min, vmax=Z_max, **surf_kwargs)
        mlab.axes(zlabel="Im(E)")

        if trajectory:
            x, y = self.get_cycle_parameters(self.t)
            _, c1, c2 = self.solve_ODE()

            for i, part in enumerate([np.real, np.imag]):
                e1, e2 = [part(self.eVals[:, n]) for n in (0, 1)]
                z = map_trajectory(c1, c2, e1, e2)
                mlab.figure(i)
                mlab.plot3d(x, y, z, tube_radius=tube_radius)
                mlab.points3d(x[0], y[0], z[0],
                              # color=line_color,
                              scale_factor=1e-1,
                              mode='sphere')

        mlab.show()

    def iso_sample_H(self, part=np.real, xmin=None, xmax=None, xN=None,
                     ymin=None, ymax=None, yN=None, zN=None):
        """Sample local eigenvalue geometry of H implicitly.

            Parameters:
            -----------
                xN, yN, zN: int
                    Number of sampling points in x, y and z direction.

            Returns:
            --------
                X, Y, Z, F: (N,N,N) ndarray
        """
        if xN is None:
            xN = 5*10**2
        if yN is None:
            yN = xN
        if zN is None:
            zN = xN

        x = np.linspace(xmin, xmax, xN)
        y = np.linspace(ymin, ymax, yN)

        # x = np.linspace(self.x_EP - 1.1*self.x_R0,
        #                 self.x_EP + 1.1*self.x_R0, xN)
        # y = np.linspace(self.y_EP - 1.1*self.y_R0,
        #                 self.y_EP + 1.1*self.y_R0, yN)

        z = np.linspace(-1, 1, zN)

        if part is np.real:
            print "real"
            f = lambda x, E: 1j*np.sign(x)*np.imag(E)
        else:
            print "imag"
            z = 1j*z
            f = lambda x, E: np.sign(x)*np.real(E)

        X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
        X, Y = [np.real(N) for N in X, Y]

        E = np.zeros((xN, yN, 2), dtype=complex)
        F = np.zeros((xN, yN, zN), dtype=complex)

        for i, xi in enumerate(x):
            for j, yj in enumerate(y):
                H = self.H(0, x=xi, y=yj)
                E[i, j, :] = c_eig(H)[0]

                char_poly = np.poly(H)

                for k, zk in enumerate(z):
                    F[i, j, k] = np.polyval(char_poly,
                                            (zk + 1j*np.sign(zk) *
                                             np.imag(E[i, j, 0])))
        return X, Y, Z, F

    def get_c_eigensystem(self):
        """Calculate the instantaneous eigenvalues and eigenvectors for
        all times t=0,...,T and remove any discontinuities."""

        # allocate temporary vectors
        eVals = np.zeros_like(self.eVals)
        eVecs_r = np.zeros_like(self.eVecs_r)
        eVecs_l = np.zeros_like(self.eVecs_l)

        # get eigenvalues and (left and right) eigenvectors at t=tn
        for n, tn in enumerate(self.t):
            eVals[n, :], eVecs_l[n, :, :], eVecs_r[n, :, :] = c_eig(self.H(tn),
                                                                    left=True)

        # check for discontinuities of first eigenvalue
        # and switch eigenvalues/eigenvectors accordingly:

        # 1) get differences between array components
        diff = np.diff(eVals[:, 0])

        # 2) if difference exceeds epsilon, switch
        epsilon = 1e-1
        mask = abs(diff) > epsilon

        # 3) assemble the arrays in a piecewise fashion at points
        #    where eigenvalue-jumps occur
        for k in mask.nonzero()[0]:
            # correct phase to obtain continuous wavefunction
            phase_0_R = np.angle(eVecs_r[k, :, 0]) - np.angle(eVecs_r[k+1, :, 1])
            phase_0_L = np.angle(eVecs_l[k, :, 0]) - np.angle(eVecs_l[k+1, :, 1])
            phase_1_R = np.angle(eVecs_r[k+1, :, 0]) - np.angle(eVecs_r[k, :, 1])
            phase_1_L = np.angle(eVecs_l[k+1, :, 0]) - np.angle(eVecs_l[k, :, 1])

            # account for phase-jump v0(k) -> v1(k+1)
            eVecs_r[k+1:,:,1] *= np.exp(+1j*phase_0_R)
            eVecs_l[k+1:,:,1] *= np.exp(+1j*phase_0_L)
            # account for phase-jump v1(k) -> v0(k+1)
            eVecs_r[:k+1,:,1] *= np.exp(+1j*phase_1_R)
            eVecs_l[:k+1,:,1] *= np.exp(+1j*phase_1_L)

            for e in eVals, eVecs_r, eVecs_l:
                e[...,0], e[...,1] = (np.concatenate((e[:k+1,...,0],
                                                      e[k+1:,...,1])),
                                      np.concatenate((e[:k+1,...,1],
                                                      e[k+1:,...,0])))

        #print np.einsum('ijk,ijk -> ik', eVecs_l, eVecs_r)

        self.eVals = eVals
        self.eVecs_l = eVecs_l
        self.eVecs_r = eVecs_r

    def _get_adiabatic_state(self):
        """Calculate the adiabatic prediction exp(1j*theta).

            Parameters:
            -----------
                n: integer
                    Determines the upper integral boundary value t[n] < T.

            Returns:
            --------
                adiabatic prediction: float
        """

        for i in (0, 1):
            E = self.eVals[:, i]
            self.theta_adiabatic[:, i] = -c_cumtrapz(E, dx=self.dt)
            self.Psi_adiabatic[:, i] = np.exp(1j*self.theta_adiabatic[:, i])

    def _find_gain_state(self):
        """Determine the (relative) gain and loss states.

        The integral int_0,T E_a(t) dt is calculated. If the imaginary part of
        the resulting integral is larger than int_0,T E_b(t), E_a is the gain
        state and nothing is done. If not, eigenvalues and eigenstates are
        interchanged.
        """

        # calculate time-integral of both eigenvalues
        intE0, intE1  = [ c_trapz(self.eVals[:,n],
                                  dx=self.dt) for n in (0,1) ]

        # change order of energy eigenvalues and eigenvectors if
        # imag(integral_E0) is smaller than imag(integral_E1)
        if np.imag(intE0) < np.imag(intE1):
            self.eVals[:,:] = self.eVals[:,::-1]
            self.eVecs_r[:,:,:] = self.eVecs_r[:,:,::-1]
            self.eVecs_l[:,:,:] = self.eVecs_l[:,:,::-1]

    def _find_lower_energy_state(self):
        """Determine the lower-energy state and sort the eigensystem such that
        the first state |0> corresponds to Re(E_0) < Re(E_1) of the second
        state |1> at time t=0."""

        if self.eVals[0, 0].real > self.eVals[0, 1].real:
            for e in self.eVals, self.eVecs_r, self.eVecs_l:
                e[..., :] = e[..., ::-1]

    def _get_init_state(self):
        """Return the initial state vector at time t=0.

        Depending on the self.init_state variable, a vector |phi_i(0)> is
        returned, with i = a, b or c/d (= linear combinations of a and b).

            Returns:
            --------
                eVec0_r: (2,) ndarray
        """

        if self.init_state == 'a':
            eVec0_r = self.eVecs_r[0,:,0]

        elif self.init_state == 'b':
            eVec0_r = self.eVecs_r[0,:,1]

        elif self.init_state == 'c':
            eVec0_r = self.eVecs_r[0,:,0] + self.eVecs_r[0,:,1]
            eVec0_l = self.eVecs_l[0,:,0] + self.eVecs_l[0,:,1]
            norm = lambda vl, vr: np.sqrt(vl.dot(vr))
            # print norm(eVec0_l, eVec0_r)
            # print norm(eVec0_r.conj(), eVec0_r)
            eVec0_r /= norm(eVec0_r.conj(), eVec0_r)

        elif self.init_state == 'd':
            phase = np.exp(1j*pi)
            eVec0_r = self.eVecs_r[0,:,0] + phase*self.eVecs_r[0,:,1]
            norm = lambda vl, vr: np.sqrt(vl.dot(vr))
            eVec0_r /= norm(eVec0_r.conj(), eVec0_r)

        return eVec0_r

    def solve_ODE(self, H=None):
        """Iteratively solve the ODE dy/dt = f(t,y) on a discretized time-grid.

            Returns:
            --------
                    t:  (N,)  ndarray
                        Time array.
                phi_a:  (N,2) ndarray
                        Overlap <phi_a|psi>.
                phi_b:  (N,2) ndarray
                        Overlap <phi_b|psi>.
        """

        if H is None:
            H = self.H

        # set initial conditions
        self.get_c_eigensystem()        # calculate eigensystem for all times
        if self.init_state_method == 'gain':
            self._find_gain_state()
        elif self.init_state_method == 'energy':
            self._find_lower_energy_state()
        self.eVec0 = self._get_init_state()

        # create ode object to solve Schroedinger equation (SE)
        ode_kwargs = {'rtol': 1e-9,
                      'atol': 1e-9}
        SE = complex_ode(lambda t, phi: -1j*H(t).dot(phi))
        SE.set_integrator('dopri5', **ode_kwargs)
        SE.set_initial_value(self.eVec0, t=0.0)

        # iterate SE
        for n, tn in enumerate(self.t):
            if SE.successful():
                self.Psi[n,:] = SE.y
                SE.integrate(SE.t + self.dt)
            else:
                raise Exception("ODE convergence error!")

        if self.calc_adiabatic_state:
            self._get_adiabatic_state()

        # replace projection of states by dot product via Einstein sum
        projection = np.einsum('ijk,ij -> ik',
                               self.eVecs_l, self.Psi)
        # use alternative means to obtain coefficients:
        #  (c1, c2) = X^-1^T psi
        # from scipy.linalg import inv
        # projection = [np.einsum('jk,j -> k', inv(self.eVecs_r[n,:]).T, self.Psi[n,:])
        #                for n, _ in enumerate(self.t)]
        # projection = np.asarray(projection)

        self.phi_a, self.phi_b = [projection[:,n] for n in (0,1)]

        return self.t, self.phi_a, self.phi_b


if __name__ == '__main__':
    pass
