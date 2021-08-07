#!/usr/bin/env python
# -*- coding: utf-8 -*-
# pylint: disable=no-member

""" Functions for performing variational inference on hidden states 

__author__: Conor Heins, Alexander Tschantz, Brennan Klein
"""

import numpy as np


from pymdp.core import utils
from pymdp.core.maths import get_joint_likelihood_seq
from pymdp.core.algos import run_fpi, run_mmp, run_mmp_testing

VANILLA = "VANILLA"
VMP = "VMP"
MMP = "MMP"
BP = "BP"
EP = "EP"
CV = "CV"

def update_posterior_states_v2(
    A,
    B,
    prev_obs,
    policies,
    prev_actions=None,
    prior=None,
    return_numpy=True,
    policy_sep_prior = True,
    **kwargs,
):
    """
    Update posterior over hidden states using marginal message passing
    """
    # safe convert to numpy
    A = utils.to_numpy(A)

    num_obs, num_states, num_modalities, num_factors = utils.get_model_dimensions(A, B)
    A = utils.to_arr_of_arr(A)
    B = utils.to_arr_of_arr(B)

    prev_obs = utils.process_observation_seq(prev_obs, num_modalities, num_obs)
    if prior is not None:
        if policy_sep_prior:
            for p_idx, policy in enumerate(policies):
                prior[p_idx] = utils.process_prior(prior[p_idx], num_factors)
        else:
            prior = utils.process_prior(prior, num_factors)

    lh_seq = get_joint_likelihood_seq(A, prev_obs, num_states)
    # print(lh_seq)

    if prev_actions is not None:
        prev_actions = np.stack(prev_actions,0)

    qs_seq_pi = utils.obj_array(len(policies))
    F = np.zeros(len(policies)) # variational free energy of policies

    if policy_sep_prior:
        for p_idx, policy in enumerate(policies):
            # get sequence and the free energy for policy
            qs_seq_pi[p_idx], F[p_idx] = run_mmp(
                lh_seq,
                B,
                policy,
                prev_actions=prev_actions,
                prior=prior[p_idx], 
                **kwargs
            )
    else:
        for p_idx, policy in enumerate(policies):
            # get sequence and the free energy for policy
            qs_seq_pi[p_idx], F[p_idx] = run_mmp(
                lh_seq,
                B,
                policy,
                prev_actions=prev_actions,
                prior=prior, 
                **kwargs
            )

    return qs_seq_pi, F

def update_posterior_states_v2_test(
    A,
    B,
    prev_obs,
    policies,
    prev_actions=None,
    prior=None,
    return_numpy=True,
    policy_sep_prior = True,
    **kwargs,
):
    """
    Update posterior over hidden states using marginal message passing
    """
    # safe convert to numpy
    A = utils.to_numpy(A)

    num_obs, num_states, num_modalities, num_factors = utils.get_model_dimensions(A, B)
    A = utils.to_arr_of_arr(A)
    B = utils.to_arr_of_arr(B)

    prev_obs = utils.process_observation_seq(prev_obs, num_modalities, num_obs)
    if prior is not None:
        if policy_sep_prior:
            for p_idx, policy in enumerate(policies):
                prior[p_idx] = utils.process_prior(prior[p_idx], num_factors)
        else:
            prior = utils.process_prior(prior, num_factors)

    lh_seq = get_joint_likelihood_seq(A, prev_obs, num_states)
    # print(lh_seq)

    if prev_actions is not None:
        prev_actions = np.stack(prev_actions,0)

    qs_seq_pi = utils.obj_array(len(policies))
    xn_seq_pi = utils.obj_array(len(policies))
    vn_seq_pi = utils.obj_array(len(policies))
    F = np.zeros(len(policies)) # variational free energy of policies

    if policy_sep_prior:
        for p_idx, policy in enumerate(policies):
            # get sequence and the free energy for policy
            qs_seq_pi[p_idx], F[p_idx], xn_seq_pi[p_idx], vn_seq_pi[p_idx] = run_mmp_testing(
                lh_seq,
                B,
                policy,
                prev_actions=prev_actions,
                prior=prior[p_idx], 
                **kwargs
            )
    else:
        for p_idx, policy in enumerate(policies):
            # get sequence and the free energy for policy
            qs_seq_pi[p_idx], F[p_idx], xn_seq_pi[p_idx], vn_seq_pi[p_idx] = run_mmp_testing(
                lh_seq,
                B,
                policy,
                prev_actions=prev_actions,
                prior=prior, 
                **kwargs
            )

    return qs_seq_pi, F, xn_seq_pi, vn_seq_pi

def average_states_over_policies(qs_pi, q_pi):
    """
    Parameters
    ----------
    `qs_seq_pi` - marginal posteriors over hidden states, per policy, at the current time point
    `q_pi` - posterior beliefs about policies  - (num_policies x 1) numpy 1D array

    Returns:
    ---------
    `qs_bma` - marginal posterior over hidden states for the current timepoint, averaged across policies according to their posterior probability given by `q_pi`
    """

    q_pi = utils.to_numpy(q_pi)

    num_factors = len(qs_pi[0]) # get the number of hidden state factors using the shape of the first-policy-conditioned posterior
    num_states = [qs_f.shape[0] for qs_f in qs_pi[0]] # get the dimensionalities of each hidden state factor 

    qs_bma = utils.obj_array(num_factors)
    for f in range(num_factors):
        qs_bma[f] = np.zeros(num_states[f])

    for p_idx, policy_weight in enumerate(q_pi):

        for f in range(num_factors):

            qs_bma[f] += qs_pi[p_idx][f] * policy_weight

    return qs_bma

def update_posterior_states(A, obs, prior=None, **kwargs):
    """
    Update marginal posterior over hidden states using mean-field fixed point iteration 
    FPI or Fixed point iteration
            - http://www.cs.cmu.edu/~guestrin/Class/10708/recitations/r9/VI-view.pdf,
            slides 13- 18
            - http://citeseerx.ist.psu.edu/viewdoc/download?doi=10.1.1.137.221&rep=rep1&type=pdf,
            slides 24 - 38
    Parameters
    ----------
    - 'A' [numpy nd.array (matrix or tensor or array-of-arrays)]:
        Observation likelihood of the generative model, mapping from hidden states to observations
        Used to invert generative model to obtain marginal likelihood over hidden states,
        given the observation
    - 'obs' [numpy 1D array, array of arrays (with 1D numpy array entries), int or tuple]:
        The observation (generated by the environment). If single modality, this can be a 1D array
        (one-hot vector representation) or an int (observation index)
        If multi-modality, this can be an array of arrays (whose entries are 1D one-hot vectors)
        or a tuple (of observation indices)
    - 'prior' [numpy 1D array, array of arrays (with 1D numpy array entries) or None]:
        Prior beliefs about hidden states, to be integrated with the marginal likelihood to obtain
         a posterior distribution.
        If None, prior is set to be equal to a flat categorical distribution (at the level of
        the individual inference functions).
        (optional)
    - **kwargs:
        List of keyword/parameter arguments corresponding to parameter values for the fixed-point iteration
        algorithm.

    Returns
    ----------
    - 'qs' [numpy 1D array, array of arrays (with 1D numpy array entries), or Categorical]:
        Marginal posterior beliefs over hidden states
    """

    num_obs, num_states, num_modalities, num_factors = utils.get_model_dimensions(A = A)
    
    obs = utils.process_observation(obs, num_modalities, num_obs)

    if prior is not None:
        prior = utils.to_arr_of_arr(prior)

    return run_fpi(A, obs, num_obs, num_states, prior, **kwargs)
   

def print_inference_methods():
    print(f"Avaliable Inference methods: {FPI}, {MMP}")
