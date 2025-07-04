# coding: utf-8

"""
Process ID producer relevant for the stitching of the DY samples.
"""

from __future__ import annotations

import abc

import law
import order

from columnflow.production import Producer
from columnflow.util import maybe_import
from columnflow.columnar_util import set_ak_column, Route

from hbt.util import IF_DATASET_IS_DY_AMCATNLO, IF_DATASET_IS_DY_POWHEG, IF_DATASET_IS_W_LNU

np = maybe_import("numpy")
ak = maybe_import("awkward")
sp = maybe_import("scipy")
maybe_import("scipy.sparse")


logger = law.logger.get_logger(__name__)

NJetsRange = tuple[int, int]
PtRange = tuple[float, float]
MRange = tuple[int, int]


class stitched_process_ids(Producer):
    """General class to calculate process ids for stitched samples.

    Individual producers should derive from this class and set the following attributes:

    :param id_table: scipy lookup table mapping processes variables (using key_func) to process ids
    :param key_func: function to generate keys for the lookup, receiving values of stitching columns
    :param stitching_columns: list of observables to use for stitching
    :param cross_check_translation_dict: dictionary to translate stitching columns to auxiliary
        fields of process objects, used for cross checking the validity of obtained ranges
    :param include_condition: condition for including stitching columns in used columns
    """

    @abc.abstractproperty
    def id_table(self) -> sp.sparse._lil.lil_matrix:
        # must be overwritten by inheriting classes
        ...

    @abc.abstractmethod
    def key_func(self, *values: ak.Array) -> int:
        # must be overwritten by inheriting classes
        ...

    @abc.abstractproperty
    def cross_check_translation_dict(self) -> dict[str, str]:
        # must be overwritten by inheriting classes
        ...

    def init_func(self, **kwargs) -> None:
        # if there is a include_condition set, apply it to both used and produced columns
        cond = lambda args: {self.include_condition(*args)} if self.include_condition else {*args}
        self.uses |= cond(self.stitching_columns or [])  # TODO: breaks for us
        self.produces |= cond(["process_id"])

    def call_func(self, events: ak.Array, **kwargs) -> ak.Array:
        """
        Assigns each event a single process id, based on the stitching values extracted per event.
        This id can be used for the stitching of the respective datasets downstream.
        """
        # ensure that each dataset has exactly one process associated to it
        if len(self.dataset_inst.processes) != 1:
            raise NotImplementedError(
                f"dataset {self.dataset_inst.name} has {len(self.dataset_inst.processes)} processes "
                "assigned, which is not yet implemented",
            )
        process_inst = self.dataset_inst.processes.get_first()

        # get stitching observables
        stitching_values = [Route(obs).apply(events) for obs in self.stitching_columns]

        # run the cross check function if defined
        if callable(self.stitching_range_cross_check):
            self.stitching_range_cross_check(process_inst, stitching_values)

        # lookup the id and check for invalid values
        process_ids = np.squeeze(np.asarray(self.id_table[self.key_func(*stitching_values)].todense()))
        invalid_mask = process_ids == 0
        if ak.any(invalid_mask):
            raise ValueError(
                f"found {sum(invalid_mask)} events that could not be assigned to a process",
            )

        # store them
        events = set_ak_column(events, "process_id", process_ids, value_type=np.int64)

        return events

    def stitching_range_cross_check(
        self,
        process_inst: order.Process,
        stitching_values: list[ak.Array],
    ) -> None:
        # define lookup for stitching observable -> process auxiliary values to compare with
        # raise a warning if a datasets was already created for a specific "bin" (leaf process),
        # but actually does not fit
        for column, values in zip(self.stitching_columns, stitching_values):
            aux_name = self.cross_check_translation_dict[str(column)]
            if not process_inst.has_aux(aux_name):
                continue
            aux_min, aux_max = process_inst.x(aux_name)
            outliers = (values < aux_min) | (values >= aux_max)
            if ak.any(outliers):
                logger.warning(
                    f"dataset {self.dataset_inst.name} is meant to contain {aux_name} values in "
                    f"the range [{aux_min}, {aux_max}), but found {ak.sum(outliers)} events "
                    "outside this range",
                )


class stiched_process_ids_nj_pt(stitched_process_ids):
    """
    Process identifier for subprocesses spanned by a jet multiplicity and an optional pt range, such
    as DY or W->lnu, which have (e.g.) "*_1j" as well as "*_1j_pt100to200" subprocesses.
    """

    # id table is set during setup, create a non-abstract class member in the meantime
    id_table = None

    # required aux fields
    njets_aux = "njets"
    pt_aux = "ptll"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # setup during setup
        self.sorted_stitching_ranges: list[tuple[NJetsRange, list[PtRange]]]

        # check that aux fields are present in cross_check_translation_dict
        for field in (self.njets_aux, self.pt_aux):
            if field not in self.cross_check_translation_dict.values():
                raise ValueError(f"field {field} must be present in cross_check_translation_dict")

    @abc.abstractproperty
    def leaf_processes(self) -> list[order.Process]:
        # must be overwritten by inheriting classes
        ...

    def setup_func(self, task: law.Task, **kwargs) -> None:
        # define stitching ranges for the DY datasets covered by this producer's dy_inclusive_dataset
        stitching_ranges: dict[NJetsRange, list[PtRange]] = {}
        for proc in self.leaf_processes:
            njets = proc.x(self.njets_aux)
            stitching_ranges.setdefault(njets, [])
            if proc.has_aux(self.pt_aux):
                stitching_ranges[njets].append(proc.x(self.pt_aux))

        # sort by the first element of the ptll range
        self.sorted_stitching_ranges = [
            (nj_range, sorted(stitching_ranges[nj_range], key=lambda ptll_range: ptll_range[0]))
            for nj_range in sorted(stitching_ranges.keys(), key=lambda nj_range: nj_range[0])
        ]

        # define the lookup table
        max_nj_bin = len(self.sorted_stitching_ranges)
        max_pt_bin = max(map(len, stitching_ranges.values()))
        self.id_table = sp.sparse.lil_matrix((max_nj_bin + 1, max_pt_bin + 1), dtype=np.int64)

        # fill it
        for proc in self.leaf_processes:
            key = self.key_func(proc.x(self.njets_aux)[0], proc.x(self.pt_aux, [-1])[0])
            self.id_table[key] = proc.id

    def key_func(
        self,
        njets: int | np.ndarray,
        pt: int | float | np.ndarray,
    ) -> tuple[int, int] | tuple[np.ndarray, np.ndarray]:
        # potentially convert single values into arrays
        single = False
        if isinstance(njets, int):
            assert isinstance(pt, (int, float))
            njets = np.array([njets], dtype=np.int32)
            pt = np.array([pt], dtype=np.float32)
            single = True

        # map into bins (index 0 means no binning)
        nj_bins = np.zeros(len(njets), dtype=np.int32)
        pt_bins = np.zeros(len(pt), dtype=np.int32)
        for nj_bin, (nj_range, pt_ranges) in enumerate(self.sorted_stitching_ranges, 1):
            # nj_bin
            nj_mask = (nj_range[0] <= njets) & (njets < nj_range[1])
            nj_bins[nj_mask] = nj_bin
            # pt_bin
            for pt_bin, (pt_min, pt_max) in enumerate(pt_ranges, 1):
                pt_mask = (pt_min <= pt) & (pt < pt_max)
                pt_bins[nj_mask & pt_mask] = pt_bin

        return (nj_bins[0], pt_bins[0]) if single else (nj_bins, pt_bins)


class stiched_process_ids_m(stitched_process_ids):
    """
    Process identifier for subprocesses spanned by the mll mass.
    """

    # id table is set during setup, create a non-abstract class member in the meantime
    id_table = None

    # required aux fields
    var_aux = "mll"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # setup during setup
        self.sorted_stitching_ranges: list[tuple[MRange]]

        # check that aux field is present in cross_check_translation_dict
        for field in (self.var_aux,):
            if field not in self.cross_check_translation_dict.values():
                raise ValueError(f"field {field} must be present in cross_check_translation_dict")

    @abc.abstractproperty
    def leaf_processes(self) -> list[order.Process]:
        # must be overwritten by inheriting classes
        ...

    def init_func(self, **kwargs) -> None:
        # if there is a include_condition set, apply it to both used and produced columns
        cond = lambda args: {self.include_condition(*args)} if self.include_condition else {*args}
        self.uses |= cond(["LHEPart.{pt,eta,mass,phi,status,pdgId}"])
        self.produces |= cond(["process_id"])

    def setup_func(self, task: law.Task, **kwargs) -> None:
        # define stitching ranges for the DY datasets covered by this producer's dy_inclusive_dataset
        stitching_ranges = [
            proc.x(self.var_aux)
            for proc in self.leaf_processes
        ]

        # sort by the first element of the range
        self.sorted_stitching_ranges = sorted(stitching_ranges, key=lambda mll_range: mll_range[0])

        # define the lookup table
        max_var_bin = len(self.sorted_stitching_ranges)
        self.id_table = sp.sparse.lil_matrix((max_var_bin + 1, 1), dtype=np.int64)

        # fill it
        for proc in self.leaf_processes:
            key = self.key_func(proc.x(self.var_aux)[0])
            self.id_table[key] = proc.id

    def key_func(
        self,
        mll: int | float | np.ndarray,
    ) -> tuple[int] | tuple[np.ndarray]:
        # potentially convert single values into arrays
        single = False
        if isinstance(mll, (int, float)):
            mll = np.array([mll], dtype=(np.int32))
            single = True

        # map into bins (index 0 means no binning)
        mll_bins = np.zeros(len(mll), dtype=np.int32)
        for mll_bin, (mll_min, mll_max) in enumerate(self.sorted_stitching_ranges, 1):
            mll_mask = (mll_min <= mll) & (mll < mll_max)
            mll_bins[mll_mask] = mll_bin

        return (mll_bins[0],) if single else (mll_bins,)

    def call_func(self, events: ak.Array, **kwargs) -> ak.Array:
        # produce the mass variable and save it as LHEmll, then call the super class
        abs_pdg_id = abs(events.LHEPart.pdgId)
        leps = events.LHEPart[(abs_pdg_id >= 11) & (abs_pdg_id <= 16) & (events.LHEPart.status == 1)]
        if ak.any((num_leps := ak.num(leps)) != 2):
            raise ValueError(f"expected exactly two leptons in the event, but found {set(num_leps)}")
        mll = leps.sum(axis=-1).mass
        events = set_ak_column(events, "LHEmll", mll, value_type=np.float32)

        return super().call_func(events, **kwargs)

    def stitching_range_cross_check(
        self,
        process_inst: order.Process,
        stitching_values: list[ak.Array],
    ) -> None:
        # TODO: this is a copy of the code above (with outlier recovery), we could factorize this a bit :)
        for i, (column, values) in enumerate(zip(self.stitching_columns, stitching_values)):
            aux_name = self.cross_check_translation_dict[str(column)]
            if not process_inst.has_aux(aux_name):
                continue
            aux_min, aux_max = process_inst.x(aux_name)
            min_outlier = values < aux_min
            max_outlier = values >= aux_max
            outliers = min_outlier | max_outlier
            if ak.any(outliers):
                logger.warning(
                    f"dataset {self.dataset_inst.name} is meant to contain {aux_name} values in "
                    f"the range [{aux_min}, {aux_max}), but found {ak.sum(outliers)} events "
                    "outside this range",
                )
                # cap values if they are within an acceptable range
                if ak.any(min_outlier):
                    recover_mask = (aux_min - values[min_outlier]) < 1.0
                    # in case not all outliers can be recovered, do not deal with these cases but raise an error
                    if not ak.all(recover_mask):
                        raise ValueError(
                            f"dataset {self.dataset_inst.name} has {ak.sum(min_outlier)} events "
                            "with values below the minimum, but not all of them can be recovered",
                        )
                    stitching_values[i] = ak.where(min_outlier, aux_min, values)
                if ak.any(max_outlier):
                    recover_mask = (values[max_outlier] - aux_max) < 1.0
                    # in case not all outliers can be recovered, do not deal with these cases but raise an error
                    if not ak.all(recover_mask):
                        raise ValueError(
                            f"dataset {self.dataset_inst.name} has {ak.sum(max_outlier)} events "
                            "with values below the maximum, but not all of them can be recovered",
                        )
                    stitching_values[i] = ak.where(max_outlier, aux_max - 1e-5, values)


process_ids_dy_amcatnlo = stiched_process_ids_nj_pt.derive("process_ids_dy_amcatnlo", cls_dict={
    "stitching_columns": ["LHE.NpNLO", "LHE.Vpt"],
    "cross_check_translation_dict": {"LHE.NpNLO": "njets", "LHE.Vpt": "ptll"},
    "include_condition": IF_DATASET_IS_DY_AMCATNLO,
    # still misses leaf_processes, must be set dynamically
})

process_ids_dy_powheg = stiched_process_ids_m.derive("process_ids_dy_powheg", cls_dict={
    "stitching_columns": ["LHEmll"],
    "cross_check_translation_dict": {"LHEmll": "mll"},
    "include_condition": IF_DATASET_IS_DY_POWHEG,
    # still misses leaf_processes, must be set dynamically
})

process_ids_w_lnu = stiched_process_ids_nj_pt.derive("process_ids_w_lnu", cls_dict={
    "stitching_columns": ["LHE.NpNLO", "LHE.Vpt"],
    "cross_check_translation_dict": {"LHE.NpNLO": "njets", "LHE.Vpt": "ptll"},
    "include_condition": IF_DATASET_IS_W_LNU,
    # still misses leaf_processes, must be set dynamically
})
