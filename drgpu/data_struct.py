"""
This file contains main class structures for some terms.
"""
import re

class Report:
    def __init__(self, path='', source_report_path=None, kernel_id=0,
                 report_content=None, source_report_content=None):
        self.path = path
        self.source_report_path = source_report_path
        # {unit_name: Unit, }
        self.units = {}
        # kernel id in ncu csv report
        self.kernel_id = kernel_id
        # Raw contents of the reports when data is provided in-memory
        self.report_content = report_content
        self.source_report_content = source_report_content


class Analysis:
    def __init__(self):
        # {stat_name: stat, } type:{str: Stat}
        self.all_stats = {}
        # {stall_reason: {inst line number: count, }, }
        self.stall_sass_code = {}
        # [None, inst1, inst2, ]
        self.source_lines = []


class Unit:
    def __init__(self, name=''):
        self.name = name
        # {name: Stat, }
        self.stats = {}

    def find_stat(self, find_name):
        return self.stats.get(find_name, None)

    def find_stat_return_0(self, find_name):
        return self.stats.get(find_name, 0)

    # testing function
    def find_stat_similar(self, find_name):
        exact = self.find_stat(find_name)
        if exact:
            return exact
        reg = re.compile(r".*%s.*" % find_name)
        stat_names = self.stats.keys()
        similars = {}
        for stat_name in stat_names:
            result = reg.findall(stat_name)
            if result:
                similars[stat_name] = self.stats.get(stat_name)
        return similars


class Stat:
    def __init__(self, aname='', araw_name='', avalue=0):
        self.name = aname
        self.raw_name = araw_name
        #TODO: every stat's default value is 0?
        self.value = avalue
        self.value_type = None
        self.suffix = ''
        self.prefix = ''
        self.avg = 0
        self.min = None
        self.max = None
        # There may be multiple max and min. So max_sm should be a list.
        self.max_sm = None
        self.min_sm = None
        self.stdDev = 0
        self.utilization = None
        # {sm6_1_1: (content, cycles, validity), }
        self.SMs_raw_value = {}
        # {sm6_1_1: value, }
        self.SMs_value = {}
        self.expression_raw = ""
        self.expression_pattern = ""
        self.description = ""
        # In the report, every stat has 3 attributes. The final value it showed in NVPDM is not sure wether it is content or cycles.
        self.content = 0
        self.validity = ''
        self.cycles = 0

    def merge(self, bstat):
        """Use this function to merge q0-q3"""
        self.value += bstat.value
        #TODO belowing has bugs. That may be caused by different gpu has different number of SMs.
        # for sm in bstat.SMs_raw_value:
        #     b_tuple = bstat.SMs_raw_value[sm]
        #     #TODO there is a bug
        #     a_tuple = self.SMs_raw_value[sm]
        #     # The last one is the validity. Should I ignore it?
        #     new_tuple = (a_tuple[0] + b_tuple[0],
        #                  a_tuple[1] + b_tuple[1], a_tuple[2])
        #     self.SMs_raw_value[sm] = new_tuple
        # for sm in bstat.SMs_value:
        #     b = bstat.SMs_value[sm]
        #     a = self.SMs_value[sm]
        #     self.SMs_value[sm] = a+b
        self.content += bstat.content
        if self.cycles is not None and bstat.cycles is not None:
            self.cycles += bstat.cycles
        # self.find_extrem_sm()

    def find_extrem_sm(self):
        if not self.SMs_value:
            print("SMs_value is empty")
            return
        #tmp_max_v = max(self.SMs_value.values())
        #tmp_max_sms = [
        #    _ for _ in self.SMs_value if self.SMs_value[_] == tmp_max_v]
        #tmp_min_v = min(self.SMs_value.values())
        #tmp_min_sms = [
        #    _ for _ in self.SMs_value if self.SMs_value[_] == tmp_min_v]


class Memory_Metrics:
    def __init__(self):
        self.bottleneck = None
        self.total_lds = None
        self.l1_hit_rate = None
        self.l1_miss_rate = None
        self.lpl1 = None
        self.bpl1 = None
        self.within_load_coalescing_ratio = None
        self.across_load_coalescing_ratio = None
        self.l1_conflict_rate = None
        self.l1_RPC = None
        self.l1_lines_per_instruction = None

        self.utlb_RPC = None
        self.utlb_miss_rate = None
        self.utlb_arb_stall_rate = None

        self.l2_miss_rate = None
        self.l2_bank_conflict_rate = None
        self.l2_RPC = None
        self.throughputs = {}

        self.access_per_activate = None
        self.compress_rate = None
        self.average_dram_banks = None

        self.shared_ld_conflict_per_request = None
        self.shared_st_conflict_per_request = None


class Configuration:
    def __init__(self):
        self.warp_size = None
        self.quadrants_per_SM = None
        self.max_number_of_showed_nodes = None
        self.max_percentage_of_showed_nodes = None
        # XX_q1, _q2 the last 3 char will be removed.
        self.number_of_suffix = 3
        self.L1_THROUGHPUT_FIX = None
        self.uTLB_THROUGHPUT_FIX = None
        self.L1_TLB_THROUGHPUT_FIX = None
        self.BYTES_PER_L2_INSTRUCTION = None
        self.L2_THROUGHPUT_FIX = None
        self.FB_THROUGHPUT_FIX = None
        self.BYTES_PER_L1_INSTRUCTION = None
        self.conflict_high_threshold = None
        self.low_activewarps_per_activecycle = None
        self.L1_THROUGHPUT_PEAK = None
        self.high_l1_throughput = None
        self.high_l1_hit_rate = None
        self.high_l1_conflict_rate = None
        self.low_access_per_activate = None
        self.low_bank_per_access = None
        self.within_load_coalescing_ratio = None
        self.low_l1_hit_rate = None
        self.high_utlb_miss_rate = None
        self.high_l2_miss_rate = None
        self.high_l2_bank_conflict_rate = None
        self.high_not_predicated_off_thread_per_inst_executed = None
        self.max_not_predicated_off_thread_per_inst_executed = None
        self.low_compress_rate = None
        self.L1_LATENCY_FIX = None
        self.uTLB_LATENCY_FIX = None
        self.l1TLB_LATENCY_FIX = None
        self.l2_latency = None
        self.fb_latency = None
        self.max_percentage_of_showed_source_code_nodes = None
        self.max_number_of_showed_source_code_nodes = None
        self.max_avtive_warps_per_SM = None
        self.compute_capability = None
