#!/usr/bin/env python3
import argparse
import os
import sys
import numpy as np
import gather
import unit_hunt
import dot_graph
import suggestions
import read_reports
import source_code_analysis
from data_struct import Node, Analysis, Report, Memory_Metrics, Configuration

def work(report, dot_graph_name, memoryconfig, memory_metrics, config):
    """
    Carry out the analysis and generate the decision tree.
    Args:
        report: The report object.
        dot_graph_name: The name of the dot graph.
        memoryconfig: The path of the memory config file.
        memory_metrics: The memory metrics object.
        config: The configuration object.
    """
    config = read_reports.read_config(memoryconfig, config)

    analysis = Analysis()
    # {stat_name: stat, } type:{str: Stat}
    all_stats = analysis.all_stats
    if dot_graph_name is None:
        (_, dot_graph_name) = os.path.split(report.path)
        (dot_graph_name, _) = os.path.splitext(dot_graph_name)
    # read reports and filter all useful stats
    read_reports.fill_stats(all_stats, report)
    if report.source_report_path:
        read_reports.fill_source_report(report, analysis)

    hw_tree = Node('Idle')
    hw_tree.suffix_label = ' of total cycles'
    retireIPC = all_stats.get('retireIPC', None)
    if retireIPC:
        root_percentage = retireIPC.value / config.quadrants_per_SM
    else:
        print("Could not get stat retireIPC")
        root_percentage = 0
    hw_tree.percentage = 1 - root_percentage

    hw_tree.prefix_label = read_reports.get_kernel_name(all_stats['kernel_name'].value) + "\n"
    hw_tree.suffix_label = ''
    best_possible = 100 * (
            1.0 - 1.0 / (np.ceil(all_stats['activewarps_per_activecycle'].value / config.quadrants_per_SM)))
    hw_tree.suffix_label += r" (lowest possible: %i%% for %i active warps)" % (
        best_possible, all_stats['activewarps_per_activecycle'].value)
    max_val = 0
    sol_unit = ""
    for unit in ['SM', 'L1', 'L2', 'Dram', 'Compute_Memory']:
        next_val = all_stats['sol_' + unit.lower()].value
        if next_val > max_val:
            sol_unit = unit
            max_val = next_val
    hw_tree.suffix_label += r"\nUtil/SOL: %.2f%% (%s)" % (max_val, sol_unit)

    hw_tree.suffix_label += r"\nIssue IPC: %.2f" % (all_stats["issueIPC"].value)

    # first level
    tmpstats = unit_hunt.warp_cant_issue(all_stats)
    gather.add_sub_branch(tmpstats, hw_tree, 1, config)
    if report.source_report_path is not None:
        source_code_analysis.add_source_code_nodes(tmpstats, hw_tree, analysis, config)

    # pipe utilization is the subbranch of shadow_pipe_throttle
    tmpstats = unit_hunt.pipe_utilization(all_stats)
    target_node = gather.find_node(hw_tree, "warp_cant_issue_pipe_throttle")
    if not target_node:
        print("Could not find the target node: warp_cant_issue_pipe_throttle")
    else:
        gather.add_pipe_throttle_branch(tmpstats, target_node, config)

    # instruction distribution is the subbranch of wait
    tmpstats = unit_hunt.instruction_distribution(all_stats)
    target_node = gather.find_node(hw_tree, "warp_cant_issue_wait")
    if not target_node:
        print("Could not find the target node: warp_cant_issue_wait")
    else:
        gather.add_sub_branch(tmpstats, target_node, 1, config)

    # warp_cant_issue_dispatch_stall
    tmpstats = unit_hunt.cant_dispatch(all_stats)
    target_node = gather.find_node(hw_tree, "warp_cant_issue_dispatch")
    if not target_node:
        print("Could not find the target node: warp_cant_issue_dispatch")
    else:
        gather.add_sub_branch(tmpstats, target_node, 1, config)

    target_node = gather.find_node(hw_tree, "warp_cant_issue_lg_throttle")
    if not target_node:
        print("Could not find the target node: warp_cant_issue_lg_throttle")
    else:
        gather.add_lg_throttle_branch(all_stats, target_node, config)

    # target_node = gather.find_node(hw_tree, "warp_cant_issue_barrier")
    # if not target_node:
    #     print("Could not find the target node: warp_cant_issue_barrier")
    # else:
    #     gather.add_sub_branch(tmpstats, target_node, 1)

    # warp_cant_issue_long_scoreboard memory
    bottleneck_unit, bottleneck_stats, memory_metrics = unit_hunt.long_scoreboard_throughput(all_stats, memory_metrics, config)
    long_scoreboard_node = gather.find_node(hw_tree, "warp_cant_issue_long_scoreboard")
    latency_stats = unit_hunt.long_scoreboard_latency(all_stats, memory_metrics, config)
    gather.add_sub_branch_for_longscoreboard_latency(latency_stats, long_scoreboard_node, all_stats, memory_metrics)
    gather.add_sub_branch_for_longscoreboard_throughput(all_stats, bottleneck_unit, bottleneck_stats, long_scoreboard_node, 1, config)

    shared_mem_stats = unit_hunt.common_function_pattern(all_stats, r'shared_ld_(\d+)b_executed')
    gather.add_shared_memory_info(all_stats, shared_mem_stats, memory_metrics)
    target_node = gather.find_node(hw_tree, "warp_cant_issue_mio_throttle")
    gather.add_branch_for_mio_throttle(all_stats, shared_mem_stats, memory_metrics, target_node, config)
    target_node = gather.find_node(hw_tree, "warp_cant_issue_short_scoreboard")
    gather.add_branch_for_short_scoreboard(all_stats, shared_mem_stats, memory_metrics, target_node, config)

    # suggestions part
    suggestions.pipe_suggest(hw_tree, all_stats)
    suggestions.barrier_suggest(hw_tree, all_stats, config)
    suggestions.branch_solving_suggest(hw_tree, all_stats, config)
    suggestions.dispatch_stall_suggest(hw_tree, all_stats)
    suggestions.drain_suggest(hw_tree, all_stats, config)
    # imc_miss_suggest(hw_tree, all_stats)
    suggestions.lg_credit_throttle_suggest(hw_tree, all_stats)
    suggestions.memory_suggest(hw_tree, all_stats, bottleneck_unit, memory_metrics, config)
    suggestions.membar_suggest(hw_tree, all_stats)
    suggestions.mio_throttle_suggest(hw_tree, all_stats, shared_mem_stats, config)
    suggestions.short_scoreboard_suggest(hw_tree, all_stats, shared_mem_stats, config)
    suggestions.wait_suggestion(hw_tree, all_stats)

    dot_graph.build_dot_graph(hw_tree, "dots/" + dot_graph_name)
    print("save to dots/" + dot_graph_name + ".svg")


def main():
    """
    Main function to parse the arguments and launch the program.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--report-path', metavar='PATH',
                        help='The path to the CSV main report generated by Nsight Compute (NCU).',
                        required=True, action='store')
    parser.add_argument('-o', '--output', metavar='FILE_NAME',
                        help='The name of the output decision tree file.', required=False,
                        action='store')
    parser.add_argument('-s', '--source', metavar='CSV_FILE_PATH',
                        help='The path to the CSV source mapping exported from NCU.',
                        required=False, action='store')
    parser.add_argument('-c', '--memoryconfig', metavar='PATH',
                        help='The path to the memory config or name of the config in mem_config',
                        required=False, action='store')
    parser.add_argument('-id', '--id', metavar='ID',
                        help='The ID of the kernel you want to analyze.', required=False,
                        dest='kernel_id', action='store')
    args = parser.parse_args()
    launch(args.report_path, args.source, args.memoryconfig,
           int(args.kernel_id) if args.kernel_id else None, args.output)


def launch(report_path: str, source: str | None, memoryconfig: str | None, kernel_id: int | None,
           output: str | None) -> None:
    """
    Launch the program with the given arguments.
    Args:
        report_path: The path of the report file.
        source: The path of the source mapping report from NCU. NCU model only.
        memoryconfig: The path of the memory config file or only file name in mem_config folder.
        kernel_id: The id of the kernel you want to analyze in exported csv files.
        output: The path of the output file to save the decision tree.
    """
    if memoryconfig is None:
        memoryconfig = sys.path[0] + '/mem_config/gtx1650.ini'
        print(
            "You didn't specify running platform for this report. DrGPU will use gtx1650.ini " \
                + "as the default GPU configuration.")
    else:
        if not memoryconfig.endswith('.ini'):
            memoryconfig += '.ini'
        if not memoryconfig.startswith('/'):
            memoryconfig = sys.path[0] + "/mem_config/" + memoryconfig
    if kernel_id is None:
        kernel_id = 0
    print(f"Report path: {report_path}")
    print(f"Source path: {source}")
    report = Report(report_path, source, kernel_id)
    memory_metrics = Memory_Metrics()
    config = Configuration()
    work(report, output, memoryconfig, memory_metrics, config)


if __name__ == "__main__":
    main()
