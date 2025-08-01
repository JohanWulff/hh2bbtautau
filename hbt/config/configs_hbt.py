# coding: utf-8

"""
Configuration of the HH → bb𝜏𝜏 analysis.
"""

from __future__ import annotations

import os
import re
import itertools
import functools

import yaml
import law
import order as od
from scinum import Number

from columnflow.tasks.external import ExternalFile as Ext
from columnflow.util import DotDict, dev_sandbox
from columnflow.config_util import (
    get_root_processes_from_campaign, add_shift_aliases, get_shifts_from_sources, verify_config_processes,
)
from columnflow.columnar_util import ColumnCollection, skip_column

from hbt import env_is_cern, force_desy_resources


thisdir = os.path.dirname(os.path.abspath(__file__))

logger = law.logger.get_logger(__name__)


def add_config(
    analysis: od.Analysis,
    campaign: od.Campaign,
    config_name: str | None = None,
    config_id: int | None = None,
    limit_dataset_files: int | None = None,
    sync_mode: bool = False,
) -> od.Config:
    # gather campaign data
    run = campaign.x.run
    year = campaign.x.year
    year2 = year % 100

    # some validations
    assert run in {2, 3}
    assert year in {2016, 2017, 2018, 2022, 2023}

    # get all root processes
    procs = get_root_processes_from_campaign(campaign)

    # create a config by passing the campaign, so id and name will be identical
    cfg = od.Config(
        name=config_name,
        id=config_id,
        campaign=campaign,
        aux={
            "sync": sync_mode,
        },
    )

    ################################################################################################
    # helpers
    ################################################################################################

    # helper to enable processes / datasets only for a specific era
    def _match_era(
        *,
        run: int | set[int] | None = None,
        year: int | set[int] | None = None,
        postfix: str | set[int] | None = None,
        tag: str | set[str] | None = None,
        nano: int | set[int] | None = None,
        sync: bool = False,
    ) -> bool:
        return (
            (run is None or campaign.x.run in law.util.make_set(run)) and
            (year is None or campaign.x.year in law.util.make_set(year)) and
            (postfix is None or campaign.x.postfix in law.util.make_set(postfix)) and
            (tag is None or campaign.has_tag(tag, mode=any)) and
            (nano is None or campaign.x.version in law.util.make_set(nano)) and
            (sync is sync_mode)
        )

    def if_era(*, values: list[str | None] | None = None, **kwargs) -> list[str]:
        return list(filter(bool, values or [])) if _match_era(**kwargs) else []

    def if_not_era(*, values: list[str | None] | None = None, **kwargs) -> list[str]:
        return list(filter(bool, values or [])) if not _match_era(**kwargs) else []

    ################################################################################################
    # processes
    ################################################################################################

    # add custom processes
    if not sync_mode:
        procs.add(
            name="v",
            id=7997,
            label="W/Z",
            processes=[procs.n.w, procs.n.z],
        )
        procs.add(
            name="multiboson",
            id=7998,
            label="Multiboson",
            processes=[procs.n.vv, procs.n.vvv],
        )
        procs.add(
            name="all_v",
            id=7996,
            label="Multiboson",
            processes=[procs.n.v, procs.n.multiboson],
        )
        procs.add(
            name="tt_multiboson",
            id=7999,
            label=r"$t\bar{t}$ + Multiboson",
            processes=[procs.n.ttv, procs.n.ttvv],
        )

    # processes we are interested in
    process_names = [
        "data",
        "tt",
        "st",
        "dy",
        "tt_multiboson",
        "all_v",
        "qcd",
        "h",
        "hh_ggf_hbb_htt_kl1_kt1",
        "hh_ggf_hbb_htt_kl0_kt1",
        "hh_ggf_hbb_htt_kl2p45_kt1",
        "hh_ggf_hbb_htt_kl5_kt1",
        "hh_ggf_hbb_htt_kl0_kt1_c21",
        "hh_ggf_hbb_htt_kl1_kt1_c23",
        "hh_vbf_hbb_htt_kv1_k2v1_kl1",
        "hh_vbf_hbb_htt_kv1_k2v0_kl1",
        "hh_vbf_hbb_htt_kvm0p962_k2v0p959_klm1p43",
        "hh_vbf_hbb_htt_kvm1p21_k2v1p94_klm0p94",
        "hh_vbf_hbb_htt_kvm1p6_k2v2p72_klm1p36",
        "hh_vbf_hbb_htt_kvm1p83_k2v3p57_klm3p39",
        # additional points besides default basis for central (broken) datasets
        # *if_era(year=2023, values=[
        #     "hh_vbf_hbb_htt_kv1p74_k2v1p37_kl14p4",
        #     "hh_vbf_hbb_htt_kvm0p012_k2v0p03_kl10p2",
        #     "hh_vbf_hbb_htt_kvm0p758_k2v1p44_klm19p3",
        #     "hh_vbf_hbb_htt_kvm2p12_k2v3p87_klm5p96",
        # ]),
        # processes from test samples, not used right now
        # "hh_vbf_hbb_htt_kv1_k2v1_kl2",
        # "hh_vbf_hbb_htt_kv1_k2v2_kl1",
        "radion_hh_ggf_hbb_htt_m450",
        "radion_hh_ggf_hbb_htt_m1200",
        "graviton_hh_ggf_hbb_htt_m450",
        "graviton_hh_ggf_hbb_htt_m1200",
    ]
    for process_name in process_names:
        if process_name in procs:
            proc = procs.get(process_name)
        elif process_name == "qcd":
            # qcd is not part of procs since there is no dataset registered for it
            from cmsdb.processes.qcd import qcd
            proc = qcd
        else:
            # development switch in case processes are not _yet_ there
            continue

        # add tags to processes
        if process_name.startswith("hh_"):
            proc.add_tag("signal")
            proc.add_tag("nonresonant_signal")
        if process_name.startswith(("graviton_hh_", "radion_hh_")):
            proc.add_tag("signal")
            proc.add_tag("resonant_signal")
        if re.match(r"^tt(|_.+)$", process_name):
            for _proc, _, _ in proc.walk_processes(include_self=True):
                _proc.add_tag({"ttbar", "tt"})
        if re.match(r"^dy(|_.+)$", process_name):
            for _proc, _, _ in proc.walk_processes(include_self=True):
                _proc.add_tag("dy")
        if re.match(r"^w_lnu(|_.+)$", process_name):
            for _proc, _, _ in proc.walk_processes(include_self=True):
                _proc.add_tag("w_lnu")

        # add the process
        cfg.add_process(proc)

    # configure colors, labels, etc
    from hbt.config.styles import stylize_processes
    stylize_processes(cfg)

    ################################################################################################
    # datasets
    ################################################################################################

    # add datasets we need to study
    dataset_names = [
        # hh ggf
        "hh_ggf_hbb_htt_kl1_kt1_powheg",
        "hh_ggf_hbb_htt_kl0_kt1_powheg",
        "hh_ggf_hbb_htt_kl2p45_kt1_powheg",
        "hh_ggf_hbb_htt_kl5_kt1_powheg",

        # hh vbf
        "hh_vbf_hbb_htt_kv1_k2v1_kl1_prv_madgraph",
        "hh_vbf_hbb_htt_kv1_k2v0_kl1_prv_madgraph",
        "hh_vbf_hbb_htt_kvm0p962_k2v0p959_klm1p43_prv_madgraph",
        "hh_vbf_hbb_htt_kvm1p21_k2v1p94_klm0p94_prv_madgraph",
        "hh_vbf_hbb_htt_kvm1p6_k2v2p72_klm1p36_prv_madgraph",
        "hh_vbf_hbb_htt_kvm1p83_k2v3p57_klm3p39_prv_madgraph",
        # additional points of central (broken) datasets
        # "hh_vbf_hbb_htt_kv1p74_k2v1p37_kl14p4_madgraph",
        # "hh_vbf_hbb_htt_kvm0p012_k2v0p03_kl10p2_madgraph",
        # "hh_vbf_hbb_htt_kvm0p758_k2v1p44_klm19p3_madgraph",
        # "hh_vbf_hbb_htt_kvm2p12_k2v3p87_klm5p96_madgraph",
        # test samples, not used right now
        # *if_era(year=2022, values=[
        #     "hh_vbf_hbb_htt_kv1_k2v1_kl2_madgraph",  # Poisson60KeepRAW for 2022post
        #     "hh_vbf_hbb_htt_kv1_k2v2_kl1_madgraph",  # Poisson60KeepRAW for 2022post
        # ]),

        # x -> hh resonances
        *if_era(year=2022, values=[
            "radion_hh_ggf_hbb_htt_m450_madgraph",
            "radion_hh_ggf_hbb_htt_m1200_madgraph",
            "graviton_hh_ggf_hbb_htt_m450_madgraph",
            "graviton_hh_ggf_hbb_htt_m1200_madgraph",
        ]),

        # ttbar
        "tt_sl_powheg",
        "tt_dl_powheg",
        "tt_fh_powheg",

        # single top
        "st_tchannel_t_4f_powheg",
        "st_tchannel_tbar_4f_powheg",
        "st_twchannel_t_sl_powheg",
        "st_twchannel_tbar_sl_powheg",
        "st_twchannel_t_dl_powheg",
        "st_twchannel_tbar_dl_powheg",
        "st_twchannel_t_fh_powheg",
        "st_twchannel_tbar_fh_powheg",
        "st_schannel_t_lep_4f_amcatnlo",
        "st_schannel_tbar_lep_4f_amcatnlo",

        # tt + v
        "ttw_wlnu_amcatnlo",
        "ttz_zqq_amcatnlo",
        "ttz_zll_m4to50_amcatnlo",
        "ttz_zll_m50toinf_amcatnlo",

        # tt + vv
        "ttww_madgraph",
        *if_not_era(year=2022, tag="preEE", values=[
            "ttwz_madgraph",  # not available in 22pre
        ]),
        "ttzz_madgraph",

        # dy, amcatnlo
        "dy_m4to10_amcatnlo",
        "dy_m10to50_amcatnlo",
        "dy_m50toinf_amcatnlo",
        "dy_m50toinf_0j_amcatnlo",
        "dy_m50toinf_1j_amcatnlo",
        "dy_m50toinf_2j_amcatnlo",
        "dy_m50toinf_1j_pt40to100_amcatnlo",
        "dy_m50toinf_1j_pt100to200_amcatnlo",
        "dy_m50toinf_1j_pt200to400_amcatnlo",
        "dy_m50toinf_1j_pt400to600_amcatnlo",
        "dy_m50toinf_1j_pt600toinf_amcatnlo",
        "dy_m50toinf_2j_pt40to100_amcatnlo",
        "dy_m50toinf_2j_pt100to200_amcatnlo",
        "dy_m50toinf_2j_pt200to400_amcatnlo",
        "dy_m50toinf_2j_pt400to600_amcatnlo",
        "dy_m50toinf_2j_pt600toinf_amcatnlo",

        # dy, powheg
        # *if_era(year=2022, values=["dy_ee_m50toinf_powheg"]),  # 50toinf only available in 2022, requires stitching
        # "dy_ee_m10to50_powheg",
        # "dy_ee_m50to120_powheg",
        # "dy_ee_m120to200_powheg",
        # "dy_ee_m200to400_powheg",
        # "dy_ee_m400to800_powheg",
        # "dy_ee_m800to1500_powheg",
        # "dy_ee_m1500to2500_powheg",
        # "dy_ee_m2500to4000_powheg",
        # "dy_ee_m4000to6000_powheg",
        # "dy_ee_m6000toinf_powheg",
        # "dy_mumu_m10to50_powheg",
        # "dy_mumu_m50to120_powheg",
        # "dy_mumu_m120to200_powheg",
        # "dy_mumu_m200to400_powheg",
        # "dy_mumu_m400to800_powheg",
        # "dy_mumu_m800to1500_powheg",
        # "dy_mumu_m1500to2500_powheg",
        # "dy_mumu_m2500to4000_powheg",
        # "dy_mumu_m4000to6000_powheg",
        # "dy_mumu_m6000toinf_powheg",
        # "dy_tautau_m10to50_powheg",
        # "dy_tautau_m50to120_powheg",
        # "dy_tautau_m120to200_powheg",
        # "dy_tautau_m200to400_powheg",
        # "dy_tautau_m400to800_powheg",
        # "dy_tautau_m800to1500_powheg",
        # "dy_tautau_m1500to2500_powheg",
        # "dy_tautau_m2500to4000_powheg",
        # "dy_tautau_m4000to6000_powheg",
        # "dy_tautau_m6000toinf_powheg",

        # w + jets
        "w_lnu_amcatnlo",
        "w_lnu_0j_amcatnlo",
        "w_lnu_1j_amcatnlo",
        "w_lnu_2j_amcatnlo",
        "w_lnu_1j_pt40to100_amcatnlo",
        "w_lnu_1j_pt100to200_amcatnlo",
        "w_lnu_1j_pt200to400_amcatnlo",
        "w_lnu_1j_pt400to600_amcatnlo",
        "w_lnu_1j_pt600toinf_amcatnlo",
        "w_lnu_2j_pt40to100_amcatnlo",
        "w_lnu_2j_pt100to200_amcatnlo",
        "w_lnu_2j_pt200to400_amcatnlo",
        "w_lnu_2j_pt400to600_amcatnlo",
        "w_lnu_2j_pt600toinf_amcatnlo",

        # z + jets (not DY but qq)
        # decided to drop z_qq for now as their contribution is negligible,
        # but we should check that again at a much later stage
        # "z_qq_1j_pt100to200_amcatnlo",
        # "z_qq_1j_pt200to400_amcatnlo",
        # "z_qq_1j_pt400to600_amcatnlo",
        # "z_qq_1j_pt600toinf_amcatnlo",
        # "z_qq_2j_pt100to200_amcatnlo",
        # "z_qq_2j_pt200to400_amcatnlo",
        # "z_qq_2j_pt400to600_amcatnlo",
        # "z_qq_2j_pt600toinf_amcatnlo",

        # vbf w/z production
        "w_vbf_wlnu_madgraph",
        "z_vbf_zll_m50toinf_madgraph",

        # vv
        "zz_pythia",
        "wz_pythia",
        "ww_pythia",

        # vvv
        "www_4f_amcatnlo",
        "wwz_4f_amcatnlo",
        "wzz_amcatnlo",
        "zzz_amcatnlo",

        # single H
        "h_ggf_htt_powheg",
        "h_ggf_hbb_powheg",
        "h_vbf_htt_powheg",
        "h_vbf_hbb_powheg",
        # "vh_hnonbb_amcatnlo",  # overlaps with dedicated wh/zh datasets, only kept as a backup!
        "wmh_wlnu_hbb_powheg",
        "wph_wlnu_hbb_powheg",
        "wph_htt_powheg",
        "wmh_htt_powheg",
        "wph_wqq_hbb_powheg",
        "wmh_wqq_hbb_powheg",
        "zh_zll_hbb_powheg",
        "zh_zqq_hbb_powheg",
        "zh_htt_powheg",
        "zh_gg_zll_hbb_powheg",
        "zh_gg_zqq_hbb_powheg",
        "zh_gg_znunu_hbb_powheg",
        "tth_hbb_powheg",
        "tth_hnonbb_powheg",

        # data
        *if_era(year=2022, tag="preEE", values=[
            f"data_{stream}_{period}" for stream in ["e", "mu", "tau"] for period in "cd"
        ]),
        *if_era(year=2022, tag="postEE", values=[
            f"data_{stream}_{period}" for stream in ["e", "mu", "tau"] for period in "efg"
        ]),
        *if_era(year=2023, tag="preBPix", values=[
            f"data_{stream}_c{v}" for stream in ["e", "mu", "tau"] for v in "1234"
        ]),
        *if_era(year=2023, tag="postBPix", values=[
            f"data_{stream}_d{v}" for stream in ["e", "mu", "tau"] for v in "12"
        ]),
    ]
    for dataset_name in dataset_names:
        # skip when in sync mode and not exiting
        if sync_mode and not campaign.has_dataset(dataset_name):
            continue

        # add the dataset
        dataset = cfg.add_dataset(campaign.get_dataset(dataset_name))
        # add tags to datasets
        if dataset.name.startswith("data_e_"):
            dataset.add_tag({"etau", "emu_from_e", "ee"})
        if dataset.name.startswith("data_mu_"):
            dataset.add_tag({"mutau", "emu_from_mu", "mumu"})
        if dataset.name.startswith("data_tau_"):
            dataset.add_tag({"tautau"})
        if dataset.name.startswith("tt_"):
            dataset.add_tag({"has_top", "ttbar", "tt"})
        if dataset.name.startswith("st_"):
            dataset.add_tag({"has_top", "single_top", "st"})
        if dataset.name.startswith("dy_"):
            dataset.add_tag("dy")
            if dataset.name.endswith("_madgraph"):
                dataset.add_tag("dy_madgraph")
            elif dataset.name.endswith("_amcatnlo"):
                dataset.add_tag("dy_amcatnlo")
            elif dataset.name.endswith("_powheg"):
                dataset.add_tag("dy_powheg")
        if re.match(r"^dy_m50toinf_\dj_(|pt.+_)amcatnlo$", dataset.name):
            dataset.add_tag("dy_stitched")
        if (
            "dy_ee_m50toinf_powheg" in cfg.datasets and
            re.match(r"^dy_ee_m.*_powheg$", dataset.name) and
            dataset.name not in {"dy_ee_m50toinf_powheg", "dy_ee_m10to50_powheg"}
        ):
            dataset.add_tag("dy_stitched")
        if dataset.name.startswith("w_lnu_"):
            dataset.add_tag("w_lnu")
        if re.match(r"^w_lnu_\dj_(|pt.+_)amcatnlo$", dataset.name):
            dataset.add_tag("w_lnu_stitched")
        # datasets that are known to have no lhe info at all
        if law.util.multi_match(dataset.name, [
            r"^(ww|wz|zz)_.*pythia$",
            r"^tt(w|z)_.*amcatnlo$",
        ]):
            dataset.add_tag("no_lhe_weights")
        # datasets that are allowed to contain some events with missing lhe infos
        # (known to happen for amcatnlo)
        if dataset.name.endswith("_amcatnlo") or re.match(r"^z_vbf_.*madgraph$", dataset.name):
            dataset.add_tag("partial_lhe_weights")
        if dataset_name.startswith("hh_"):
            dataset.add_tag("signal")
            dataset.add_tag("nonresonant_signal")
            if dataset_name.startswith("hh_ggf_"):
                dataset.add_tag("ggf")
            elif dataset_name.startswith("hh_vbf_"):
                dataset.add_tag("vbf")
        if dataset_name.startswith(("graviton_hh_", "radion_hh_")):
            dataset.add_tag("signal")
            dataset.add_tag("resonant_signal")
            if dataset_name.startswith(("graviton_hh_ggf_", "radion_hh_ggf")):
                dataset.add_tag("ggf")
            elif dataset_name.startswith(("graviton_hh_vbf_", "radion_hh_vbf")):
                dataset.add_tag("vbf")

        # bad ecalBadCalibFilter MET filter in 2022 data
        # https://twiki.cern.ch/twiki/bin/view/CMS/MissingETOptionalFiltersRun2?rev=172#ECal_BadCalibration_Filter_Flag
        # https://cms-talk.web.cern.ch/t/noise-met-filters-in-run-3/63346/5
        if year == 2022 and dataset.is_data and dataset.x.era in "FG":
            dataset.add_tag("needs_custom_ecalBadCalibFilter")

        # apply an optional limit on the number of files
        if limit_dataset_files:
            for info in dataset.info.values():
                info.n_files = min(info.n_files, limit_dataset_files)

        # apply synchronization settings
        if sync_mode:
            # only first file per
            for info in dataset.info.values():
                info.n_files = 1

    # verify that the root process of each dataset is part of any of the registered processes
    if not sync_mode:
        verify_config_processes(cfg, warn=True)

    ################################################################################################
    # task defaults and groups
    ################################################################################################

    # default objects
    cfg.x.default_calibrator = "default"
    cfg.x.default_selector = "default"
    cfg.x.default_reducer = "default"
    cfg.x.default_producer = "default"
    cfg.x.default_ml_model = None
    cfg.x.default_inference_model = "default_no_shifts"
    cfg.x.default_categories = ("all",)
    cfg.x.default_variables = ("njet", "nbtag", "res_pdnn_hh", "res_dnn_hh")
    cfg.x.default_hist_producer = "default"

    # process groups for conveniently looping over certain processs
    # (used in wrapper_factory and during plotting)
    cfg.x.process_groups = {
        "signals": [
            "hh_ggf_hbb_htt_kl1_kt1",
            "hh_vbf_hbb_htt_kv1_k2v1_kl1",
        ],
        "signals_ggf": [
            "hh_ggf_hbb_htt_kl0_kt1",
            "hh_ggf_hbb_htt_kl1_kt1",
            "hh_ggf_hbb_htt_kl2p45_kt1",
            "hh_ggf_hbb_htt_kl5_kt1",
        ],
        "backgrounds": (backgrounds := [
            "dy",
            "tt",
            "qcd",
            "st",
            "tt_multiboson",
            "multiboson",
            "v",
            "h",
            "ewk",
        ]),
        "dy_split": [
            "dy_m4to10", "dy_m10to50",
            "dy_m50toinf_0j",
            "dy_m50toinf_1j_pt40to100", "dy_m50toinf_1j_pt100to200", "dy_m50toinf_1j_pt200to400",
            "dy_m50toinf_1j_pt400to600", "dy_m50toinf_1j_pt600toinf",
            "dy_m50toinf_2j_pt40to100", "dy_m50toinf_2j_pt100to200", "dy_m50toinf_2j_pt200to400",
            "dy_m50toinf_2j_pt400to600", "dy_m50toinf_2j_pt600toinf",
        ],
        "dy_split_no_incl": [
            "dy_m4to10", "dy_m10to50",
            "dy_m50toinf_0j", "dy_m50toinf_1j", "dy_m50toinf_2j",
            "dy_m50toinf_1j_pt0to40", "dy_m50toinf_1j_pt40to100", "dy_m50toinf_1j_pt100to200",
            "dy_m50toinf_1j_pt200to400", "dy_m50toinf_1j_pt400to600", "dy_m50toinf_1j_pt600toinf",
            "dy_m50toinf_2j_pt0to40", "dy_m50toinf_2j_pt40to100", "dy_m50toinf_2j_pt100to200",
            "dy_m50toinf_2j_pt200to400", "dy_m50toinf_2j_pt400to600", "dy_m50toinf_2j_pt600toinf",
        ],
        "sm_ggf": (sm_ggf_group := ["hh_ggf_hbb_htt_kl1_kt1", *backgrounds]),
        "sm": (sm_group := ["hh_ggf_hbb_htt_kl1_kt1", "hh_vbf_hbb_htt_kv1_k2v1_kl1", *backgrounds]),
        "sm_ggf_data": ["data"] + sm_ggf_group,
        "sm_data": ["data"] + sm_group,
    }

    # define inclusive datasets for the stitched process identification with corresponding leaf processes
    if run == 3 and not sync_mode:
        # drell-yan, amcatnlo
        if "dy_m50toinf_amcatnlo" in cfg.datasets:
            cfg.x.dy_amcatnlo_stitching = {
                "m50toinf": {
                    "inclusive_dataset": cfg.datasets.n.dy_m50toinf_amcatnlo,
                    "leaf_processes": [
                        # the following processes cover the full njet and pt phasespace
                        procs.n.dy_m50toinf_0j,
                        *(
                            procs.get(f"dy_m50toinf_{nj}j_pt{pt}")
                            for nj in [1, 2]
                            for pt in ["0to40", "40to100", "100to200", "200to400", "400to600", "600toinf"]
                        ),
                        procs.n.dy_m50toinf_ge3j,
                    ],
                },
            }
        # drell-yan, powheg
        if year == 2022 and "dy_ee_m50toinf_powheg" in cfg.datasets:
            cfg.x.dy_powheg_stitching = {
                "ee_m50toinf": {
                    "inclusive_dataset": cfg.datasets.n.dy_ee_m50toinf_powheg,
                    "leaf_processes": [
                        # the following processes cover the full inv mass phasespace
                        *(
                            procs.get(f"dy_ee_m{mass}")
                            for mass in ["50to120", "120to200", "200to400", "400to800", "800to1500", "1500to2500", "2500to4000", "4000to6000", "6000toinf"]  # noqa: E501
                        ),
                    ],
                },
            }
        # w+jets
        cfg.x.w_lnu_stitching = {
            "incl": {
                "inclusive_dataset": cfg.datasets.n.w_lnu_amcatnlo,
                "leaf_processes": [
                    # the following processes cover the full njet and pt phasespace
                    procs.n.w_lnu_0j,
                    *(
                        procs.get(f"w_lnu_{nj}j_pt{pt}")
                        for nj in [1, 2]
                        for pt in ["0to40", "40to100", "100to200", "200to400", "400to600", "600toinf"]
                    ),
                    procs.n.w_lnu_ge3j,
                ],
            },
        }

    # dataset groups for conveniently looping over certain datasets
    # (used in wrapper_factory and during plotting)
    cfg.x.dataset_groups = {
        "data": (data_group := [dataset.name for dataset in cfg.datasets if dataset.is_data]),
        "backgrounds": (backgrounds := [
            # ! this "mindlessly" includes all non-signal MC datasets from above
            dataset.name for dataset in cfg.datasets
            if dataset.is_mc and not dataset.has_tag("signal")
        ]),
        "backgrounds_unstitched": (backgrounds_unstitched := [
            dataset.name for dataset in cfg.datasets
            if (
                dataset.is_mc and
                not dataset.has_tag("signal") and
                not dataset.has_tag({"dy_stitched", "w_lnu_stitched"}, mode=any)
            )
        ]),
        "sm_ggf": (sm_ggf_group := ["hh_ggf_hbb_htt_kl1_kt1_powheg", *backgrounds]),
        "sm": (sm_group := [
            "hh_ggf_hbb_htt_kl1_kt1_powheg",
            "hh_vbf_hbb_htt_kv1_k2v1_kl1_*madgraph",
            *backgrounds,
        ]),
        "sm_unstitched": (sm_group_unstitched := [
            "hh_ggf_hbb_htt_kl1_kt1_powheg",
            "hh_vbf_hbb_htt_kv1_k2v1_kl1_*madgraph",
            *backgrounds_unstitched,
        ]),
        "sm_ggf_data": data_group + sm_ggf_group,
        "sm_data": data_group + sm_group,
        "sm_data_unstitched": data_group + sm_group_unstitched,
        "dy": [dataset.name for dataset in cfg.datasets if dataset.has_tag("dy")],
        "w_lnu": [dataset.name for dataset in cfg.datasets if dataset.has_tag("w_lnu")],
    }

    # category groups for conveniently looping over certain categories
    # (used during plotting)
    cfg.x.category_groups = {}

    # variable groups for conveniently looping over certain variables
    # (used during plotting)
    cfg.x.variable_groups = {
        "hh": (hh := [f"hh_{var}" for var in ["energy", "mass", "pt", "eta", "phi", "dr"]]),
        "dilep": (dilep := [f"dilep_{var}" for var in ["energy", "mass", "pt", "eta", "phi", "dr"]]),
        "dijet": (dijet := [f"dijet_{var}" for var in ["energy", "mass", "pt", "eta", "phi", "dr"]]),
        "default": [
            *dijet, *dilep, *hh,
            "mu1_pt", "mu1_eta", "mu1_phi", "mu2_pt", "mu2_eta", "mu2_phi",
            "e1_pt", "e1_eta", "e1_phi", "e2_pt", "e2_eta", "e2_phi",
            "tau1_pt", "tau1_eta", "tau1_phi", "tau2_pt", "tau2_eta", "tau2_phi",
        ],
    }

    # shift groups for conveniently looping over certain shifts
    # (used during plotting)
    cfg.x.shift_groups = {}

    # selector step groups for conveniently looping over certain steps
    # (used in cutflow tasks)
    cfg.x.selector_step_groups = {
        "all": [],
        "none": ["json"],
        "default": ["json", "trigger", "met_filter", "jet_veto_map", "lepton", "jet2"],
        "no_jet": ["json", "trigger", "met_filter", "jet_veto_map", "lepton"],
    }
    cfg.x.default_selector_steps = "all"

    # plotting overwrites
    from hbt.config.styles import setup_plot_styles
    setup_plot_styles(cfg)

    ################################################################################################
    # luminosity and normalization
    ################################################################################################

    # lumi values in 1/pb (= 1000/fb)
    # https://twiki.cern.ch/twiki/bin/view/CMS/LumiRecommendationsRun2?rev=7
    # https://twiki.cern.ch/twiki/bin/view/CMS/LumiRecommendationsRun3?rev=25
    # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis
    # difference pre-post VFP: https://cds.cern.ch/record/2854610/files/DP2023_006.pdf
    # Lumis for Run3 within the Twiki are outdated as stated here:
    # https://cms-talk.web.cern.ch/t/luminosity-in-run2023c/116859/2
    # Run3 Lumis can be calculated with brilcalc tool https://twiki.cern.ch/twiki/bin/view/CMS/BrilcalcQuickStart?rev=15
    # CClub computed this already: https://gitlab.cern.ch/cclubbtautau/AnalysisCore/-/issues/49
    if year == 2016 and campaign.has_tag("preVFP"):
        cfg.x.luminosity = Number(19_500, {
            "lumi_13TeV_2016": 0.01j,
            "lumi_13TeV_correlated": 0.006j,
        })
    elif year == 2016 and campaign.has_tag("postVFP"):
        cfg.x.luminosity = Number(16_800, {
            "lumi_13TeV_2016": 0.01j,
            "lumi_13TeV_correlated": 0.006j,
        })
    elif year == 2017:
        cfg.x.luminosity = Number(41_480, {
            "lumi_13TeV_2017": 0.02j,
            "lumi_13TeV_1718": 0.006j,
            "lumi_13TeV_correlated": 0.009j,
        })
    elif year == 2018:
        cfg.x.luminosity = Number(59_830, {
            "lumi_13TeV_2017": 0.015j,
            "lumi_13TeV_1718": 0.002j,
            "lumi_13TeV_correlated": 0.02j,
        })
    elif year == 2022 and campaign.has_tag("preEE"):
        cfg.x.luminosity = Number(7_980.4541, {
            "lumi_13p6TeV_correlated": 0.014j,
        })
    elif year == 2022 and campaign.has_tag("postEE"):
        cfg.x.luminosity = Number(26_671.6097, {
            "lumi_13p6TeV_correlated": 0.014j,
        })
    elif year == 2023 and campaign.has_tag("preBPix"):
        cfg.x.luminosity = Number(18_062.6591, {
            "lumi_13p6TeV_correlated": 0.013j,
        })
    elif year == 2023 and campaign.has_tag("postBPix"):
        cfg.x.luminosity = Number(9_693.1301, {
            "lumi_13p6TeV_correlated": 0.013j,
        })
    else:
        assert False

    # minimum bias cross section in mb (milli) for creating PU weights, values from
    # https://twiki.cern.ch/twiki/bin/view/CMS/PileupJSONFileforData?rev=52#Recommended_cross_section
    cfg.x.minbias_xs = Number(69.2, 0.046j)

    ################################################################################################
    # met settings
    ################################################################################################

    if run == 2:
        cfg.x.met_name = "MET"
        cfg.x.raw_met_name = "RawMET"
    elif run == 3:
        cfg.x.met_name = "PuppiMET"
        cfg.x.raw_met_name = "RawPuppiMET"
    else:
        assert False

    # name of the MET phi correction set
    # (used in the met_phi calibrator)
    if run == 2:
        cfg.x.met_phi_correction_set = r"{variable}_metphicorr_pfmet_{data_source}"

    ################################################################################################
    # jet settings
    # TODO: keep a single table somewhere that configures all settings: btag correlation, year
    #       dependence, usage in calibrator, etc
    ################################################################################################

    # common jec/jer settings configuration
    if run == 2:
        # https://cms-jerc.web.cern.ch/Recommendations/#run-2
        # https://twiki.cern.ch/twiki/bin/view/CMS/JECDataMC?rev=204
        # https://twiki.cern.ch/twiki/bin/view/CMS/JetResolution?rev=109
        jec_campaign = f"Summer19UL{year2}{campaign.x.postfix}"
        jec_version = {2016: "V7", 2017: "V5", 2018: "V5"}[year]
        jer_campaign = f"Summer{'20' if year == 2016 else '19'}UL{year2}{campaign.x.postfix}"
        jer_version = "JR" + {2016: "V3", 2017: "V2", 2018: "V2"}[year]
        jet_type = "AK4PFchs"
    elif run == 3:
        # https://cms-jerc.web.cern.ch/Recommendations/#2022
        jerc_postfix = {
            (2022, ""): "_22Sep2023",
            (2022, "EE"): "_22Sep2023",
            (2023, ""): "Prompt23",
            (2023, "BPix"): "Prompt23",
        }[(year, campaign.x.postfix)]
        jec_campaign = f"Summer{year2}{campaign.x.postfix}{jerc_postfix}"
        jec_version = {
            (2022, ""): "V2",
            (2022, "EE"): "V2",
            (2023, ""): "V2",
            (2023, "BPix"): "V3",
        }[(year, campaign.x.postfix)]
        jer_campaign = f"Summer{year2}{campaign.x.postfix}{jerc_postfix}"
        # special "Run" fragment in 2023 jer campaign
        if year == 2023:
            jer_campaign += f"_Run{'Cv1234' if campaign.has_tag('preBPix') else 'D'}"
        jer_version = "JR" + {2022: "V1", 2023: "V1"}[year]
        jet_type = "AK4PFPuppi"
    else:
        assert False

    cfg.x.jec = DotDict.wrap({
        "Jet": {
            "campaign": jec_campaign,
            "version": jec_version,
            "data_per_era": True if year == 2022 else False,  # 2022 JEC has the era as a corrlib input argument
            "jet_type": jet_type,
            "levels": ["L1FastJet", "L2Relative", "L2L3Residual", "L3Absolute"],
            "levels_for_type1_met": ["L1FastJet"],
            "uncertainty_sources": list(filter(bool, [
                # "AbsoluteStat",
                # "AbsoluteScale",
                # "AbsoluteSample",
                # "AbsoluteFlavMap",
                # "AbsoluteMPFBias",
                # "Fragmentation",
                # "SinglePionECAL",
                # "SinglePionHCAL",
                # "FlavorQCD",
                # "TimePtEta",
                # "RelativeJEREC1",
                # "RelativeJEREC2",
                # "RelativeJERHF",
                # "RelativePtBB",
                # "RelativePtEC1",
                # "RelativePtEC2",
                # "RelativePtHF",
                # "RelativeBal",
                # "RelativeSample",
                # "RelativeFSR",
                # "RelativeStatFSR",
                # "RelativeStatEC",
                # "RelativeStatHF",
                # "PileUpDataMC",
                # "PileUpPtRef",
                # "PileUpPtBB",
                # "PileUpPtEC1",
                # "PileUpPtEC2",
                # "PileUpPtHF",
                # "PileUpMuZero",
                # "PileUpEnvelope",
                # "SubTotalPileUp",
                # "SubTotalRelative",
                # "SubTotalPt",
                # "SubTotalScale",
                # "SubTotalAbsolute",
                # "SubTotalMC",
                "Total",
                # "TotalNoFlavor",
                # "TotalNoTime",
                # "TotalNoFlavorNoTime",
                # "FlavorZJet",
                # "FlavorPhotonJet",
                # "FlavorPureGluon",
                # "FlavorPureQuark",
                # "FlavorPureCharm",
                # "FlavorPureBottom",
                "CorrelationGroupMPFInSitu",
                "CorrelationGroupIntercalibration",
                "CorrelationGroupbJES",
                "CorrelationGroupFlavor",
                "CorrelationGroupUncorrelated",
            ])),
        },
    })

    # JER
    cfg.x.jer = DotDict.wrap({
        "Jet": {
            "campaign": jer_campaign,
            "version": jer_version,
            "jet_type": jet_type,
        },
    })

    # updated jet id
    from columnflow.production.cms.jet import JetIdConfig
    cfg.x.jet_id = JetIdConfig(corrections={"AK4PUPPI_Tight": 2, "AK4PUPPI_TightLeptonVeto": 3})
    cfg.x.fatjet_id = JetIdConfig(corrections={"AK8PUPPI_Tight": 2, "AK8PUPPI_TightLeptonVeto": 3})

    # trigger sf corrector
    cfg.x.jet_trigger_corrector = "jetlegSFs"

    ################################################################################################
    # tau settings
    ################################################################################################

    # tau tagger name
    # (needed by TECConfig below as well as tau selection)
    if run == 2:
        # TODO: still correct? what about 2p5?
        cfg.x.tau_tagger = "DeepTau2017v2p1"
    elif run == 3:
        # https://twiki.cern.ch/twiki/bin/view/CMS/TauIDRecommendationForRun3?rev=9
        cfg.x.tau_tagger = "DeepTau2018v2p5"
    else:
        assert False

    # tec config
    from columnflow.calibration.cms.tau import TECConfig
    corrector_kwargs = {"wp": "Medium", "wp_VSe": "VVLoose"} if run == 3 else {}
    cfg.x.tec = TECConfig(tagger=cfg.x.tau_tagger, corrector_kwargs=corrector_kwargs)

    # tau ID working points
    if campaign.x.version < 10:
        cfg.x.tau_id_working_points = DotDict.wrap({
            "tau_vs_e": {"vvvloose": 1, "vvloose": 2, "vloose": 4, "loose": 8, "medium": 16, "tight": 32, "vtight": 64, "vvtight": 128},  # noqa: E501
            "tau_vs_jet": {"vvvloose": 1, "vvloose": 2, "vloose": 4, "loose": 8, "medium": 16, "tight": 32, "vtight": 64, "vvtight": 128},  # noqa: E501
            "tau_vs_mu": {"vloose": 1, "loose": 2, "medium": 4, "tight": 8},
        })
    else:
        cfg.x.tau_id_working_points = DotDict.wrap({
            "tau_vs_e": {"vvvloose": 1, "vvloose": 2, "vloose": 3, "loose": 4, "medium": 5, "tight": 6, "vtight": 7, "vvtight": 8},  # noqa: E501
            "tau_vs_jet": {"vvvloose": 1, "vvloose": 2, "vloose": 3, "loose": 4, "medium": 5, "tight": 6, "vtight": 7, "vvtight": 8},  # noqa: E501
            "tau_vs_mu": {"vloose": 1, "loose": 2, "medium": 3, "tight": 4},
        })

    # tau trigger working points
    cfg.x.tau_trigger_working_points = DotDict.wrap({
        "id_vs_jet_v0": "VVLoose",
        "id_vs_jet_gv0": ("Loose", "VVLoose"),
        "id_vs_mu_single": "Tight",
        "id_vs_mu_cross": "VLoose",
        "id_vs_e_single": "VVLoose",
        "id_vs_e_cross": "VVLoose",
        "trigger_corr": "VVLoose",
    })

    # tau trigger correctors
    cfg.x.tau_trigger_corrector = "tau_trigger"
    cfg.x.tau_trigger_corrector_cclub = "tauTriggerSF"

    ################################################################################################
    # electron settings
    ################################################################################################

    # names of electron correction sets and working points
    from columnflow.production.cms.electron import ElectronSFConfig
    from columnflow.calibration.cms.egamma import EGammaCorrectionConfig
    if run == 2:
        # SFs
        e_postfix = ""
        if year == 2016:
            e_postfix = {"APV": "preVFP", "": "postVFP"}[campaign.x.postfix]
        cfg.x.electron_sf_names = ElectronSFConfig(
            correction="UL-Electron-ID-SF",
            campaign=f"{year}{e_postfix}",
            working_point="wp80iso",
        )
        # eec and eer
        cfg.x.eec = EGammaCorrectionConfig(
            correction_set="Scale",
            value_type="total_correction",
            uncertainty_type="total_uncertainty",
        )
        cfg.x.eer = EGammaCorrectionConfig(
            correction_set="Smearing",
            compound=False,
            value_type="rho",
            uncertainty_type="err_rho",
        )
    elif run == 3:
        # SFs
        if year == 2022:
            e_postfix = {"": "Re-recoBCD", "EE": "Re-recoE+PromptFG"}[campaign.x.postfix]
        elif year == 2023:
            e_postfix = {"": "PromptC", "BPix": "PromptD"}[campaign.x.postfix]
        else:
            assert False
        cfg.x.electron_sf_names = ElectronSFConfig(
            correction="Electron-ID-SF",
            campaign=f"{year}{e_postfix}",
            working_point="wp80iso",
        )
        cfg.x.electron_trigger_sf_names = ElectronSFConfig(
            correction="Electron-HLT-SF",
            campaign=f"{year}{e_postfix}",
            hlt_path="HLT_SF_Ele30_TightID",
        )
        cfg.x.single_trigger_electron_data_effs_cfg = ElectronSFConfig(
            correction="Electron-HLT-DataEff",
            campaign=f"{year}{e_postfix}",
            hlt_path="HLT_SF_Ele30_TightID",
        )
        cfg.x.single_trigger_electron_mc_effs_cfg = ElectronSFConfig(
            correction="Electron-HLT-McEff",
            campaign=f"{year}{e_postfix}",
            hlt_path="HLT_SF_Ele30_TightID",
        )
        cfg.x.cross_trigger_electron_data_effs_cfg = ElectronSFConfig(
            correction="Electron-HLT-DataEff",
            campaign=f"{year}{e_postfix}",
            hlt_path="HLT_SF_Ele24_TightID",
        )
        cfg.x.cross_trigger_electron_mc_effs_cfg = ElectronSFConfig(
            correction="Electron-HLT-McEff",
            campaign=f"{year}{e_postfix}",
            hlt_path="HLT_SF_Ele24_TightID",
        )
        # eec and eer
        if year == 2022:
            e_tag = {"": "preEE", "EE": "postEE"}[campaign.x.postfix]
        elif year == 2023:
            # note the upper-case IX
            e_tag = {"": "preBPIX", "BPix": "postBPIX"}[campaign.x.postfix]
        else:
            assert False
        cfg.x.eec = EGammaCorrectionConfig(
            correction_set=f"EGMScale_Compound_Ele_{year}{e_tag}",
            value_type="scale",
            uncertainty_type="escale",
            compound=True,
        )
        cfg.x.eer = EGammaCorrectionConfig(
            correction_set=f"EGMSmearAndSyst_ElePTsplit_{year}{e_tag}",
            value_type="smear",
            uncertainty_type="esmear",
        )
    else:
        assert False

    ################################################################################################
    # muon settings
    ################################################################################################

    # names of muon correction sets and working points
    # (used in the muon producer)
    from columnflow.production.cms.muon import MuonSFConfig
    if run == 2:
        cfg.x.muon_sf_names = MuonSFConfig(correction="NUM_TightRelIso_DEN_TightIDandIPCut")
    elif run == 3:
        cfg.x.muon_sf_names = MuonSFConfig(correction="NUM_TightPFIso_DEN_TightID")
        cfg.x.muon_trigger_sf_names = MuonSFConfig(
            correction="NUM_IsoMu24_DEN_CutBasedIdTight_and_PFIsoTight",
        )
        cfg.x.single_trigger_muon_data_effs_cfg = MuonSFConfig(
            correction="NUM_IsoMu24_DEN_CutBasedIdTight_and_PFIsoTight_DATAeff",
        )
        cfg.x.single_trigger_muon_mc_effs_cfg = MuonSFConfig(
            correction="NUM_IsoMu24_DEN_CutBasedIdTight_and_PFIsoTight_MCeff",
        )
        cfg.x.cross_trigger_muon_data_effs_cfg = MuonSFConfig(
            correction="NUM_IsoMu20_DEN_CutBasedIdTight_and_PFIsoTight_DATAeff",
        )
        cfg.x.cross_trigger_muon_mc_effs_cfg = MuonSFConfig(
            correction="NUM_IsoMu20_DEN_CutBasedIdTight_and_PFIsoTight_MCeff",
        )

    else:
        assert False

    ################################################################################################
    # b tagging
    ################################################################################################

    # b-tag working points
    btag_key = f"{year}{campaign.x.postfix}"
    if run == 2:
        # https://twiki.cern.ch/twiki/bin/view/CMS/BtagRecommendation106XUL16preVFP?rev=6
        # https://twiki.cern.ch/twiki/bin/view/CMS/BtagRecommendation106XUL16postVFP?rev=8
        # https://twiki.cern.ch/twiki/bin/view/CMS/BtagRecommendation106XUL17?rev=15
        # https://twiki.cern.ch/twiki/bin/view/CMS/BtagRecommendation106XUL18?rev=18
        cfg.x.btag_working_points = DotDict.wrap({
            "deepjet": {
                "loose": {"2016APV": 0.0508, "2016": 0.0480, "2017": 0.0532, "2018": 0.0490}[btag_key],
                "medium": {"2016APV": 0.2598, "2016": 0.2489, "2017": 0.3040, "2018": 0.2783}[btag_key],
                "tight": {"2016APV": 0.6502, "2016": 0.6377, "2017": 0.7476, "2018": 0.7100}[btag_key],
            },
            "deepcsv": {
                "loose": {"2016APV": 0.2027, "2016": 0.1918, "2017": 0.1355, "2018": 0.1208}[btag_key],
                "medium": {"2016APV": 0.6001, "2016": 0.5847, "2017": 0.4506, "2018": 0.4168}[btag_key],
                "tight": {"2016APV": 0.8819, "2016": 0.8767, "2017": 0.7738, "2018": 0.7665}[btag_key],
            },
            # https://cms.cern.ch/iCMS/jsp/db_notes/noteInfo.jsp?cmsnoteid=CMS%20AN-2021/005 chapter 4.5 in v12
            "particleNetMD": {
                "hp": {"2016APV": 0.9883, "2016": 0.9883, "2017": 0.9870, "2018": 0.9880}[btag_key],
                "mp": {"2016APV": 0.9737, "2016": 0.9735, "2017": 0.9714, "2018": 0.9734}[btag_key],
                "lp": {"2016APV": 0.9088, "2016": 0.9137, "2017": 0.9105, "2018": 0.9172}[btag_key],
            },
        })
    elif run == 3:
        # https://btv-wiki.docs.cern.ch/ScaleFactors/Run3Summer22
        # https://btv-wiki.docs.cern.ch/ScaleFactors/Run3Summer22EE
        # https://btv-wiki.docs.cern.ch/ScaleFactors/Run3Summer23
        # https://btv-wiki.docs.cern.ch/ScaleFactors/Run3Summer23BPix
        cfg.x.btag_working_points = DotDict.wrap({
            "deepjet": {
                "loose": {"2022": 0.0583, "2022EE": 0.0614, "2023": 0.0479, "2023BPix": 0.048}[btag_key],
                "medium": {"2022": 0.3086, "2022EE": 0.3196, "2023": 0.2431, "2023BPix": 0.2435}[btag_key],
                "tight": {"2022": 0.7183, "2022EE": 0.73, "2023": 0.6553, "2023BPix": 0.6563}[btag_key],
                "xtight": {"2022": 0.8111, "2022EE": 0.8184, "2023": 0.7667, "2023BPix": 0.7671}[btag_key],
                "xxtight": {"2022": 0.9512, "2022EE": 0.9542, "2023": 0.9459, "2023BPix": 0.9483}[btag_key],
            },
            "particleNet": {
                "loose": {"2022": 0.047, "2022EE": 0.0499, "2023": 0.0358, "2023BPix": 0.0359}[btag_key],
                "medium": {"2022": 0.245, "2022EE": 0.2605, "2023": 0.1917, "2023BPix": 0.1919}[btag_key],
                "tight": {"2022": 0.6734, "2022EE": 0.6915, "2023": 0.6172, "2023BPix": 0.6133}[btag_key],
                "xtight": {"2022": 0.7862, "2022EE": 0.8033, "2023": 0.7515, "2023BPix": 0.7544}[btag_key],
                "xxtight": {"2022": 0.961, "2022EE": 0.9664, "2023": 0.9659, "2023BPix": 0.9688}[btag_key],
            },
            "robustParticleTransformer": {
                "loose": {"2022": 0.0849, "2022EE": 0.0897, "2023": 0.0681, "2023BPix": 0.0683}[btag_key],
                "medium": {"2022": 0.4319, "2022EE": 0.451, "2023": 0.3487, "2023BPix": 0.3494}[btag_key],
                "tight": {"2022": 0.8482, "2022EE": 0.8604, "2023": 0.7969, "2023BPix": 0.7994}[btag_key],
                "xtight": {"2022": 0.9151, "2022EE": 0.9234, "2023": 0.8882, "2023BPix": 0.8877}[btag_key],
                "xxtight": {"2022": 0.9874, "2022EE": 0.9893, "2023": 0.9883, "2023BPix": 0.9883}[btag_key],
            },
            # TODO: fallback to run2, due to missing wp values
            # https://cms.cern.ch/iCMS/jsp/db_notes/noteInfo.jsp?cmsnoteid=CMS%20AN-2021/005 chapter 4.5 in v12
            # performance studies for run 3 available and show improvements:
            # https://cds.cern.ch/record/2904691/files/DP2024_055.pdf

            "particleNetMD": {
                "hp": {"2022": 0.9883, "2022EE": 0.9883, "2023": 0.9870, "2023BPix": 0.9880}[btag_key],
                "mp": {"2022": 0.9737, "2022EE": 0.9735, "2023": 0.9714, "2023BPix": 0.9734}[btag_key],
                "lp": {"2022": 0.9088, "2022EE": 0.9137, "2023": 0.9105, "2023BPix": 0.9172}[btag_key],
            },
        })
    else:
        assert False

    # JEC uncertainty sources propagated to btag scale factors
    # (names derived from contents in BTV correctionlib file)
    cfg.x.btag_sf_jec_sources = [
        "",  # same as "Total"
        "Absolute",
        "AbsoluteMPFBias",
        "AbsoluteScale",
        "AbsoluteStat",
        f"Absolute_{year}",
        "BBEC1",
        f"BBEC1_{year}",
        "EC2",
        f"EC2_{year}",
        "FlavorQCD",
        "Fragmentation",
        "HF",
        f"HF_{year}",
        "PileUpDataMC",
        "PileUpPtBB",
        "PileUpPtEC1",
        "PileUpPtEC2",
        "PileUpPtHF",
        "PileUpPtRef",
        "RelativeBal",
        "RelativeFSR",
        "RelativeJEREC1",
        "RelativeJEREC2",
        "RelativeJERHF",
        "RelativePtBB",
        "RelativePtEC1",
        "RelativePtEC2",
        "RelativePtHF",
        "RelativeSample",
        f"RelativeSample_{year}",
        "RelativeStatEC",
        "RelativeStatFSR",
        "RelativeStatHF",
        "SinglePionECAL",
        "SinglePionHCAL",
        "TimePtEta",
    ]

    from columnflow.production.cms.btag import BTagSFConfig
    cfg.x.btag_sf_deepjet = BTagSFConfig(
        correction_set="deepJet_shape",
        jec_sources=cfg.x.btag_sf_jec_sources,
        discriminator="btagDeepFlavB",
    )
    if run == 3:
        cfg.x.btag_sf_pnet = BTagSFConfig(
            correction_set="particleNet_shape",
            jec_sources=cfg.x.btag_sf_jec_sources,
            discriminator="btagPNetB",
        )

    ################################################################################################
    # dataset / process specific methods
    ################################################################################################

    # top pt reweighting
    # https://twiki.cern.ch/twiki/bin/view/CMS/TopPtReweighting?rev=31
    from columnflow.production.cms.top_pt_weight import TopPtWeightConfig
    cfg.x.top_pt_weight = TopPtWeightConfig(
        params={
            "a": 0.0615,
            "a_up": 0.0615 * 1.5,
            "a_down": 0.0615 * 0.5,
            "b": -0.0005,
            "b_up": -0.0005 * 1.5,
            "b_down": -0.0005 * 0.5,
        },
        pt_max=500.0,
    )

    # dy specific methods
    if run == 3:
        from columnflow.production.cms.dy import DrellYanConfig
        dy_era = f"{year}"
        if year == 2022:
            dy_era += "preEE" if campaign.has_tag("preEE") else "postEE"
        elif year == 2023:
            dy_era += "preBPix" if campaign.has_tag("preBPix") else "postBPix"
        else:
            assert False

        # dy reweighting
        # https://cms-higgs-leprare.docs.cern.ch/htt-common/DY_reweight
        cfg.x.dy_weight_config = DrellYanConfig(
            era=dy_era,
            order="NLO",
            correction="DY_pTll_reweighting",
            unc_correction="DY_pTll_reweighting_N_uncertainty",
        )

        # dy boson recoil correction
        # https://cms-higgs-leprare.docs.cern.ch/htt-common/V_recoil
        cfg.x.dy_recoil_config = DrellYanConfig(
            era=dy_era,
            order="NLO",
            correction="Recoil_correction_Rescaling",
            unc_correction="Recoil_correction_Uncertainty",
        )

    ################################################################################################
    # shifts
    ################################################################################################

    # load jec sources
    with open(os.path.join(thisdir, "jec_sources.yaml"), "r") as f:
        all_jec_sources = yaml.load(f, yaml.Loader)["names"]

    # register shifts
    cfg.add_shift(name="nominal", id=0)

    cfg.add_shift(name="tune_up", id=1, type="shape", tags={"disjoint_from_nominal"})
    cfg.add_shift(name="tune_down", id=2, type="shape", tags={"disjoint_from_nominal"})

    cfg.add_shift(name="hdamp_up", id=3, type="shape", tags={"disjoint_from_nominal"})
    cfg.add_shift(name="hdamp_down", id=4, type="shape", tags={"disjoint_from_nominal"})

    cfg.add_shift(name="mtop_up", id=5, type="shape", tags={"disjoint_from_nominal"})
    cfg.add_shift(name="mtop_down", id=6, type="shape", tags={"disjoint_from_nominal"})

    cfg.add_shift(name="minbias_xs_up", id=7, type="shape")
    cfg.add_shift(name="minbias_xs_down", id=8, type="shape")
    add_shift_aliases(
        cfg,
        "minbias_xs",
        {
            "pu_weight": "pu_weight_{name}",
            "normalized_pu_weight": "normalized_pu_weight_{name}",
        },
    )

    cfg.add_shift(name="top_pt_up", id=9, type="shape")
    cfg.add_shift(name="top_pt_down", id=10, type="shape")
    add_shift_aliases(cfg, "top_pt", {"top_pt_weight": "top_pt_weight_{direction}"})

    for jec_source in cfg.x.jec.Jet.uncertainty_sources:
        idx = all_jec_sources.index(jec_source)
        cfg.add_shift(
            name=f"jec_{jec_source}_up",
            id=5000 + 2 * idx,
            type="shape",
            tags={"jec"},
            aux={"jec_source": jec_source},
        )
        cfg.add_shift(
            name=f"jec_{jec_source}_down",
            id=5001 + 2 * idx,
            type="shape",
            tags={"jec"},
            aux={"jec_source": jec_source},
        )
        add_shift_aliases(
            cfg,
            f"jec_{jec_source}",
            {
                "Jet.pt": "Jet.pt_{name}",
                "Jet.mass": "Jet.mass_{name}",
                f"{cfg.x.met_name}.pt": f"{cfg.x.met_name}.pt_{{name}}",
                f"{cfg.x.met_name}.phi": f"{cfg.x.met_name}.phi_{{name}}",
            },
        )
        # TODO: check the JEC de/correlation across years and the interplay with btag weights
        if ("" if jec_source == "Total" else jec_source) in cfg.x.btag_sf_jec_sources:
            add_shift_aliases(
                cfg,
                f"jec_{jec_source}",
                {
                    "normalized_btag_deepjet_weight": "normalized_btag_deepjet_weight_{name}",
                    "normalized_njet_btag_deepjet_weight": "normalized_njet_btag_deepjet_weight_{name}",
                    "normalized_btag_pnet_weight": "normalized_btag_pnet_weight_{name}",
                    "normalized_njet_btag_pnet_weight": "normalized_njet_btag_pnet_weight_{name}",
                },
            )

    cfg.add_shift(name="jer_up", id=6000, type="shape", tags={"jer"})
    cfg.add_shift(name="jer_down", id=6001, type="shape", tags={"jer"})
    add_shift_aliases(
        cfg,
        "jer",
        {
            "Jet.pt": "Jet.pt_{name}",
            "Jet.mass": "Jet.mass_{name}",
            f"{cfg.x.met_name}.pt": f"{cfg.x.met_name}.pt_{{name}}",
            f"{cfg.x.met_name}.phi": f"{cfg.x.met_name}.phi_{{name}}",
        },
    )

    for i, (match, dm) in enumerate(itertools.product(["jet", "e"], [0, 1, 10, 11])):
        cfg.add_shift(name=f"tec_{match}_dm{dm}_up", id=20 + 2 * i, type="shape", tags={"tec"})
        cfg.add_shift(name=f"tec_{match}_dm{dm}_down", id=21 + 2 * i, type="shape", tags={"tec"})
        add_shift_aliases(
            cfg,
            f"tec_{match}_dm{dm}",
            {
                "Tau.pt": "Tau.pt_{name}",
                "Tau.mass": "Tau.mass_{name}",
                f"{cfg.x.met_name}.pt": f"{cfg.x.met_name}.pt_{{name}}",
                f"{cfg.x.met_name}.phi": f"{cfg.x.met_name}.phi_{{name}}",
            },
        )

    # start at id=50
    cfg.x.tau_unc_names = [
        "jet_dm0", "jet_dm1", "jet_dm10", "jet_dm11",
        "e_barrel", "e_endcap",
        "mu_0p0To0p4", "mu_0p4To0p8", "mu_0p8To1p2", "mu_1p2To1p7", "mu_1p7To2p3",
    ]
    for i, unc in enumerate(cfg.x.tau_unc_names):
        cfg.add_shift(name=f"tau_{unc}_up", id=50 + 2 * i, type="shape")
        cfg.add_shift(name=f"tau_{unc}_down", id=51 + 2 * i, type="shape")
        add_shift_aliases(cfg, f"tau_{unc}", {"tau_weight": f"tau_weight_{unc}_" + "{direction}"})

    cfg.add_shift(name="e_up", id=90, type="shape")
    cfg.add_shift(name="e_down", id=91, type="shape")
    add_shift_aliases(cfg, "e", {"electron_weight": "electron_weight_{direction}"})

    # electron shifts
    # TODO: energy corrections are currently only available for 2022 (Jan 2025)
    #       include them when available
    if run == 3 and year == 2022:
        logger.debug("adding ees and eer shifts")
        cfg.add_shift(name="ees_up", id=92, type="shape", tags={"eec"})
        cfg.add_shift(name="ees_down", id=93, type="shape", tags={"eec"})
        add_shift_aliases(
            cfg,
            "ees",
            {
                "Electron.pt": "Electron.pt_scale_{direction}",
            },
        )

        cfg.add_shift(name="eer_up", id=94, type="shape", tags={"eer"})
        cfg.add_shift(name="eer_down", id=95, type="shape", tags={"eer"})
        add_shift_aliases(
            cfg,
            "eer",
            {
                "Electron.pt": "Electron.pt_res_{direction}",
            },
        )

    cfg.add_shift(name="mu_up", id=100, type="shape")
    cfg.add_shift(name="mu_down", id=101, type="shape")
    add_shift_aliases(cfg, "mu", {"muon_weight": "muon_weight_{direction}"})

    cfg.x.btag_unc_names = [
        "hf", "lf",
        f"hfstats1_{year}", f"hfstats2_{year}",
        f"lfstats1_{year}", f"lfstats2_{year}",
        "cferr1", "cferr2",
    ]
    for i, unc in enumerate(cfg.x.btag_unc_names):
        cfg.add_shift(name=f"btag_{unc}_up", id=110 + 2 * i, type="shape")
        cfg.add_shift(name=f"btag_{unc}_down", id=111 + 2 * i, type="shape")
        add_shift_aliases(
            cfg,
            f"btag_{unc}",
            {
                "normalized_btag_deepjet_weight": f"normalized_btag_deepjet_weight_{unc}_" + "{direction}",
                "normalized_njet_btag_deepjet_weight": f"normalized_njet_btag_deepjet_weight_{unc}_" + "{direction}",
                # TODO: pnet here, or is this another shift? probably the latter
            },
        )

    cfg.add_shift(name="pdf_up", id=130, type="shape", tags={"lhe_weight"})
    cfg.add_shift(name="pdf_down", id=131, type="shape", tags={"lhe_weight"})
    add_shift_aliases(
        cfg,
        "pdf",
        {
            "pdf_weight": "pdf_weight_{direction}",
            "normalized_pdf_weight": "normalized_pdf_weight_{direction}",
        },
    )

    cfg.add_shift(name="murmuf_up", id=140, type="shape", tags={"lhe_weight"})
    cfg.add_shift(name="murmuf_down", id=141, type="shape", tags={"lhe_weight"})
    add_shift_aliases(
        cfg,
        "murmuf",
        {
            "murmuf_weight": "murmuf_weight_{direction}",
            "normalized_murmuf_weight": "normalized_murmuf_weight_{direction}",
        },
    )

    cfg.add_shift(name="isr_up", id=150, type="shape")
    cfg.add_shift(name="isr_down", id=151, type="shape")
    add_shift_aliases(
        cfg,
        "isr",
        {
            "isr_weight": "isr_weight_{direction}",
            "normalized_isr_weight": "normalized_isr_weight_{direction}",
        },
    )
    cfg.add_shift(name="fsr_up", id=155, type="shape")
    cfg.add_shift(name="fsr_down", id=156, type="shape")
    add_shift_aliases(
        cfg,
        "fsr",
        {
            "fsr_weight": "fsr_weight_{direction}",
            "normalized_fsr_weight": "normalized_fsr_weight_{direction}",
        },
    )

    # trigger scale factors
    trigger_legs = ["e", "mu", "tau_dm0", "tau_dm1", "tau_dm10", "tau_dm11", "jet"]
    for i, leg in enumerate(trigger_legs):
        cfg.add_shift(name=f"trigger_{leg}_up", id=180 + 2 * i, type="shape")
        cfg.add_shift(name=f"trigger_{leg}_down", id=181 + 2 * i, type="shape")
        add_shift_aliases(cfg, f"trigger_{leg}", {"trigger_weight": f"trigger_weight_{leg}_{{direction}}"})

    ################################################################################################
    # external files
    ################################################################################################

    cfg.x.external_files = DotDict()

    # helper
    def add_external(name, value):
        if isinstance(value, dict):
            value = DotDict.wrap(value)
        cfg.x.external_files[name] = value

    if run == 2:
        json_postfix = ""
        if year == 2016:
            json_postfix = f"{'pre' if campaign.has_tag('preVFP') else 'post'}VFP"
        json_pog_era = f"{year}{json_postfix}_UL"
        json_mirror = "/afs/cern.ch/user/m/mrieger/public/mirrors/jsonpog-integration-b7a48c75"
    elif run == 3:
        json_pog_era = f"{year}_Summer{year2}{campaign.x.postfix}"
        json_mirror = "/afs/cern.ch/user/m/mrieger/public/mirrors/jsonpog-integration-b7a48c75"
        trigger_json_mirror = "https://gitlab.cern.ch/cclubbtautau/AnalysisCore/-/archive/59ae66c4a39d3e54afad5733895c33b1fb511c47/AnalysisCore-59ae66c4a39d3e54afad5733895c33b1fb511c47.tar.gz"  # noqa: E501
        campaign_tag = ""
        for tag in ("preEE", "postEE", "preBPix", "postBPix"):
            if campaign.has_tag(tag, mode=any):
                if campaign_tag:
                    raise ValueError(f"Multiple campaign tags found: {cfg.x.campaign_tag} and {tag}")
                campaign_tag = tag
        cclub_eras = f"{year}{campaign_tag}"
    else:
        assert False

    # common files
    # (versions in the end are for hashing in cases where file contents changed but paths did not)
    add_external("lumi", {
        "golden": {
            2016: ("/afs/cern.ch/cms/CAF/CMSCOMM/COMM_DQM/certification/Collisions16/13TeV/Legacy_2016/Cert_271036-284044_13TeV_Legacy2016_Collisions16_JSON.txt", "v1"),  # noqa: E501
            2017: ("/afs/cern.ch/cms/CAF/CMSCOMM/COMM_DQM/certification/Collisions17/13TeV/Legacy_2017/Cert_294927-306462_13TeV_UL2017_Collisions17_GoldenJSON.txt", "v1"),  # noqa: E501
            2018: ("/afs/cern.ch/cms/CAF/CMSCOMM/COMM_DQM/certification/Collisions18/13TeV/Legacy_2018/Cert_314472-325175_13TeV_Legacy2018_Collisions18_JSON.txt", "v1"),  # noqa: E501
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=161#Year_2022
            2022: ("https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions22/Cert_Collisions2022_355100_362760_Golden.json", "v1"),  # noqa: E501
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=161#Year_2023
            2023: ("https://cms-service-dqmdc.web.cern.ch/CAF/certification/Collisions23/Cert_Collisions2023_366442_370790_Golden.json", "v1"),  # noqa: E501
        }[year],
        "normtag": {
            2016: ("/afs/cern.ch/user/l/lumipro/public/Normtags/normtag_PHYSICS.json", "v1"),
            2017: ("/afs/cern.ch/user/l/lumipro/public/Normtags/normtag_PHYSICS.json", "v1"),
            2018: ("/afs/cern.ch/user/l/lumipro/public/Normtags/normtag_PHYSICS.json", "v1"),
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=161#Year_2022
            2022: ("/cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_BRIL.json", "v1"),
            # https://twiki.cern.ch/twiki/bin/view/CMS/PdmVRun3Analysis?rev=161#Year_2023
            2023: ("/cvmfs/cms-bril.cern.ch/cms-lumi-pog/Normtags/normtag_BRIL.json", "v1"),
        }[year],
    })
    # pileup weight corrections
    add_external("pu_sf", (f"{json_mirror}/POG/LUM/{json_pog_era}/puWeights.json.gz", "v1"))
    # jet energy correction
    add_external("jet_jerc", (f"{json_mirror}/POG/JME/{json_pog_era}/jet_jerc.json.gz", "v1"))
    # jet veto map
    add_external("jet_veto_map", (f"{json_mirror}/POG/JME/{json_pog_era}/jetvetomaps.json.gz", "v1"))
    # btag scale factor
    add_external("btag_sf_corr", (f"{json_mirror}/POG/BTV/{json_pog_era}/btagging.json.gz", "v1"))
    # Tobias' tautauNN (https://github.com/uhh-cms/tautauNN)
    add_external("res_pdnn", ("/afs/cern.ch/work/m/mrieger/public/hbt/external_files/res_models/res_prod3/model_fold0.tgz", "v1"))  # noqa: E501
    # non-parametric (flat) training up to mX = 800 GeV
    add_external("res_dnn", ("/afs/cern.ch/work/m/mrieger/public/hbt/external_files/res_models/res_prod3_nonparam/model_fold0.tgz", "v1"))  # noqa: E501
    # non-parametric regression from the resonant analysis
    add_external("reg_dnn", ("/afs/cern.ch/work/m/mrieger/public/hbt/models/reg_prod1_nonparam/model_fold0_seed0.tgz", "v1"))  # noqa: E501
    add_external("reg_dnn_moe", ("/afs/cern.ch/work/m/mrieger/public/hbt/models/reg_prod1_nonparam/model_fold0_moe.tgz", "v1"))  # noqa: E501

    # run specific files
    if run == 2:
        # tau energy correction and scale factors
        add_external("tau_sf", (f"{json_mirror}/POG/TAU/{json_pog_era}/tau.json.gz", "v1"))
        # tau trigger scale factors
        add_external("tau_trigger_sf", (f"{json_mirror}/POG/TAU/{json_pog_era}/tau.json.gz", "v1"))
        # electron scale factors
        add_external("electron_sf", (f"{json_mirror}/POG/EGM/{json_pog_era}/electron.json.gz", "v1"))
        # muon scale factors
        add_external("muon_sf", (f"{json_mirror}/POG/MUO/{json_pog_era}/muon_Z.json.gz", "v1"))
        # met phi correction
        add_external("met_phi_corr", (f"{json_mirror}/POG/JME/{json_pog_era}/met.json.gz", "v1"))
        # hh-btag repository with TF saved model directories trained on Run2 UL samples
        add_external("electron_ss", (f"{json_mirror}/POG/EGM/{json_pog_era}/electronSS.json.gz", "v1"))
        add_external("hh_btag_repo", Ext(
            "/afs/cern.ch/work/m/mrieger/public/hbt/external_files/hh-btag-master-d7a71eb3.tar.gz",
            subpaths=DotDict(even="hh-btag-master/models/HHbtag_v2_par_0", odd="hh-btag-master/models/HHbtag_v2_par_1"),
            version="v2",
        ))
    elif run == 3:
        # updated jet id
        add_external("jet_id", (f"{json_mirror}/POG/JME/{json_pog_era}/jetid.json.gz", "v1"))
        # muon scale factors
        add_external("muon_sf", (f"{json_mirror}/POG/MUO/{json_pog_era}/muon_Z.json.gz", "v1"))

        # electron scale factors
        add_external("electron_sf", (f"{json_mirror}/POG/EGM/{json_pog_era}/electron.json.gz", "v1"))
        # electron energy correction and smearing
        add_external("electron_ss", (f"{json_mirror}/POG/EGM/{json_pog_era}/electronSS_EtDependent.json.gz", "v1"))
        # hh-btag repository with TF saved model directories trained on 22+23 samples using pnet
        add_external("hh_btag_repo", Ext(
            "/afs/cern.ch/work/m/mrieger/public/hbt/external_files/hh-btag-master-d7a71eb3.tar.gz",
            subpaths=DotDict(even="hh-btag-master/models/HHbtag_v3_par_0", odd="hh-btag-master/models/HHbtag_v3_par_1"),
            version="v3",
        ))
        # tau energy correction and scale factors
        if year == 2022:
            tau_pog_era = f"{year}_{'pre' if campaign.has_tag('preEE') else 'post'}EE"
            tau_pog_era_cclub = f"{year}{'pre' if campaign.has_tag('preEE') else 'post'}EE"
        elif year == 2023:
            tau_pog_era = f"{year}_{'pre' if campaign.has_tag('preBPix') else 'post'}BPix"
            tau_pog_era_cclub = f"{year}{'pre' if campaign.has_tag('preBPix') else 'post'}BPix"
        else:
            assert False
        add_external("tau_sf", (f"{json_mirror}/POG/TAU/{json_pog_era}/tau_DeepTau2018v2p5_{tau_pog_era}.json.gz", "v1"))  # noqa: E501
        # dy weight and recoil corrections
        add_external("dy_weight_sf", ("/afs/cern.ch/work/m/mrieger/public/mirrors/external_files/DY_pTll_weights_v3.json.gz", "v1"))  # noqa: E501
        add_external("dy_recoil_sf", ("/afs/cern.ch/work/m/mrieger/public/mirrors/external_files/Recoil_corrections_v3.json.gz", "v1"))  # noqa: E501

        # trigger scale factors
        trigger_sf_internal_subpath = "AnalysisCore-59ae66c4a39d3e54afad5733895c33b1fb511c47/data/TriggerScaleFactors"
        add_external("trigger_sf", Ext(
            f"{trigger_json_mirror}",
            subpaths=DotDict(
                muon=f"{trigger_sf_internal_subpath}/{cclub_eras}/temporary_MuHlt_abseta_pt.json",
                cross_muon=f"{trigger_sf_internal_subpath}/{cclub_eras}/CrossMuTauHlt.json",
                electron=f"{trigger_sf_internal_subpath}/{cclub_eras}/electronHlt.json",
                cross_electron=f"{trigger_sf_internal_subpath}/{cclub_eras}/CrossEleTauHlt.json",
                tau=f"{trigger_sf_internal_subpath}/{cclub_eras}/tau_trigger_DeepTau2018v2p5_{tau_pog_era_cclub}.json",
                jet=f"{trigger_sf_internal_subpath}/{cclub_eras}/ditaujet_jetleg_SFs_{campaign_tag}.json",
            ),
            version="v1",
        ))

    else:
        assert False

    ################################################################################################
    # reductions
    ################################################################################################

    # target file size after MergeReducedEvents in MB
    cfg.x.reduced_file_size = 512.0

    # columns to keep after certain steps
    cfg.x.keep_columns = DotDict.wrap({
        # !! note that this set is used by the cf_default reducer
        "cf.ReduceEvents": {
            # mandatory
            ColumnCollection.MANDATORY_COFFEA,
            # event info
            "deterministic_seed",
            # object info
            "Jet.{pt,eta,phi,mass,hadronFlavour,puId,hhbtag,btagPNet*,btagDeep*,deterministic_seed,chHEF,neHEF,chEmEF,neEmEF,muEF,chMultiplicity,neMultiplicity}",  # noqa: E501
            "HHBJet.{pt,eta,phi,mass,hadronFlavour,puId,hhbtag,btagPNet*,btagDeep*,deterministic_seed}",
            "NonHHBJet.{pt,eta,phi,mass,hadronFlavour,puId,hhbtag,btagPNet*,btagDeep*,deterministic_seed}",
            "VBFJet.{pt,eta,phi,mass,hadronFlavour,puId,hhbtag,btagPNet*,btagDeep*,deterministic_seed}",
            "FatJet.*",
            "SubJet{1,2}.*",
            "Electron.*", *skip_column("Electron.{track_cov,gsf}*"),
            "Muon.*", skip_column("Muon.track_cov*"),
            "Tau.*", skip_column("Tau.track_cov*"),
            f"{cfg.x.met_name}.{{pt,phi,significance,covXX,covXY,covYY}}",
            "PV.npvs",
            # keep all columns added during selection and reduction, but skip cutflow features
            ColumnCollection.ALL_FROM_SELECTOR,
            skip_column("cutflow.*"),
        },
        "cf.MergeSelectionMasks": {
            "cutflow.*",
        },
        "cf.UniteColumns": {
            "*", *skip_column("*_{up,down}"),
        },
    })

    ################################################################################################
    # weights
    ################################################################################################

    # configurations for all possible event weight columns as keys in an OrderedDict,
    # mapped to shift instances they depend on
    # (this info is used by weight producers)
    get_shifts = functools.partial(get_shifts_from_sources, cfg)
    cfg.x.event_weights = DotDict({
        "normalization_weight": [],
        "normalization_weight_inclusive": [],
        "pdf_weight": get_shifts("pdf"),
        "murmuf_weight": get_shifts("murmuf"),
        "normalized_pu_weight": get_shifts("minbias_xs"),
        "normalized_isr_weight": get_shifts("isr"),
        "normalized_fsr_weight": get_shifts("fsr"),
        # TODO: enable again once we have btag cuts
        # "normalized_njet_btag_deepjet_weight": get_shifts(*(f"btag_{unc}" for unc in cfg.x.btag_unc_names)),
        "electron_weight": get_shifts("e"),
        "muon_weight": get_shifts("mu"),
        "tau_weight": get_shifts(*(f"tau_{unc}" for unc in cfg.x.tau_unc_names)),
        "trigger_weight": get_shifts(*(f"trigger_{leg}" for leg in trigger_legs)),
    })

    # define per-dataset event weights
    for dataset in cfg.datasets:
        if dataset.has_tag("ttbar"):
            dataset.x.event_weights = {"top_pt_weight": get_shifts("top_pt")}
        if dataset.has_tag("dy"):
            dataset.x.event_weights = {"dy_weight": []}  # TODO: list dy weight unceratinties

    cfg.x.shift_groups = {
        "jec": [
            shift_inst.name for shift_inst in cfg.shifts
            if shift_inst.has_tag(("jec", "jer"))
        ],
        "lepton_sf": [
            shift_inst.name for shift_inst in (*get_shifts("e"), *get_shifts("mu"))
        ],
        "tec": [
            shift_inst.name for shift_inst in cfg.shifts
            if shift_inst.has_tag("tec")
        ],
        "eec": [
            shift_inst.name for shift_inst in cfg.shifts
            if shift_inst.has_tag(("ees", "eer"))
        ],
        "ees": [
            shift_inst.name for shift_inst in cfg.shifts
            if shift_inst.has_tag("ees")
        ],
        "eer": [
            shift_inst.name for shift_inst in cfg.shifts
            if shift_inst.has_tag("eer")
        ],
        "btag_sf": [
            shift_inst.name for shift_inst in get_shifts(*(f"btag_{unc}" for unc in cfg.x.btag_unc_names))
        ],
        "pdf": [shift_inst.name for shift_inst in get_shifts("pdf")],
        "murmuf": [shift_inst.name for shift_inst in get_shifts("murmuf")],
        "pu": [shift_inst.name for shift_inst in get_shifts("minbias_xs")],
    }

    ################################################################################################
    # external configs: channels, categories, met filters, triggers, variables
    ################################################################################################

    # channels
    cfg.add_channel(name="etau", id=1, label=r"$e\tau_{h}$")
    cfg.add_channel(name="mutau", id=2, label=r"$\mu\tau_{h}$")
    cfg.add_channel(name="tautau", id=3, label=r"$\tau_{h}\tau_{h}$")
    cfg.add_channel(name="ee", id=4, label=r"$ee$")
    cfg.add_channel(name="mumu", id=5, label=r"$\mu\mu$")
    cfg.add_channel(name="emu", id=6, label=r"$e\mu$")

    # add categories
    from hbt.config.categories import add_categories
    add_categories(cfg)

    # add variables
    from hbt.config.variables import add_variables
    add_variables(cfg)

    # add met filters
    from hbt.config.met_filters import add_met_filters
    add_met_filters(cfg)

    # add triggers
    if year == 2016:
        from hbt.config.triggers import add_triggers_2016
        add_triggers_2016(cfg)
    elif year == 2017:
        from hbt.config.triggers import add_triggers_2017
        add_triggers_2017(cfg)
    elif year == 2018:
        from hbt.config.triggers import add_triggers_2018
        add_triggers_2018(cfg)
    elif year == 2022:
        from hbt.config.triggers import add_triggers_2022
        add_triggers_2022(cfg)
    elif year == 2023:
        from hbt.config.triggers import add_triggers_2023
        add_triggers_2023(cfg)
    else:
        raise False

    ################################################################################################
    # LFN settings
    ################################################################################################

    # custom method and sandbox for determining dataset lfns
    cfg.x.get_dataset_lfns = None
    cfg.x.get_dataset_lfns_sandbox = None

    # whether to validate the number of obtained LFNs in GetDatasetLFNs
    cfg.x.validate_dataset_lfns = limit_dataset_files is None and not sync_mode

    # custom lfn retrieval method in case the underlying campaign is custom uhh
    if cfg.campaign.x("custom", {}).get("creator") == "uhh":
        def get_dataset_lfns(
            dataset_inst: od.Dataset,
            shift_inst: od.Shift,
            dataset_key: str,
        ) -> list[str]:
            # destructure dataset_key into parts and create the store path
            dataset_id, full_campaign, tier = dataset_key.split("/")[1:]
            main_campaign, sub_campaign = full_campaign.split("-", 1)
            path = f"store/{dataset_inst.data_source}/{main_campaign}/{dataset_id}/{tier}/{sub_campaign}/0"

            # nanogen version that is appended to the fs base
            # note: this feature is not yet used as we do not have different prod* versions per dataset yet
            # nanogen_version = dataset_inst.x("nanogen_version", None) or cfg.campaign.x.custom["nanogen_version"]

            # lookup file systems to use
            fs = f"wlcg_fs_{cfg.campaign.x.custom['name']}"
            local_fs = f"local_fs_{cfg.campaign.x.custom['name']}"
            # ammend when located on CERN resources
            if not force_desy_resources and env_is_cern:
                fs += "_eos"
                local_fs += "_eos"

            # create the lfn base directory, local or remote
            dir_cls = law.wlcg.WLCGDirectoryTarget
            if law.config.has_section(local_fs):
                base = law.target.file.remove_scheme(law.config.get_expanded(local_fs, "base"))
                # if os.path.exists(os.path.join(base, nanogen_version)):
                if os.path.exists(base):
                    dir_cls = law.LocalDirectoryTarget
                    fs = local_fs
            # lfn_base = dir_cls(nanogen_version, fs=fs).child(path, type="d")
            lfn_base = dir_cls(path, fs=fs)

            # loop though files and interpret paths as lfns
            return sorted(
                "/" + lfn_base.child(basename, type="f").path.lstrip("/")
                for basename in lfn_base.listdir(pattern="*.root")
            )

        # define the lfn retrieval function
        cfg.x.get_dataset_lfns = get_dataset_lfns

        # define a custom sandbox
        cfg.x.get_dataset_lfns_sandbox = dev_sandbox("bash::$CF_BASE/sandboxes/cf.sh")

        # define custom remote fs's to look at
        cfg.x.get_dataset_lfns_remote_fs = lambda dataset_inst: [
            f"local_fs_{cfg.campaign.x.custom['name']}",
            f"wlcg_fs_{cfg.campaign.x.custom['name']}",
        ]

    return cfg
