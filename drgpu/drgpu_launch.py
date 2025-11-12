#!/usr/bin/env python3
"""
Launch the DrGPU tool.
"""
import os
from pathlib import Path
import configparser
from typing import List
import numpy as np
from drgpu import gather
from drgpu import unit_hunt
from drgpu import dot_graph
from drgpu import suggestions
from drgpu import read_reports
from drgpu import source_code_analysis
from drgpu.data_struct import Analysis, Report, Memory_Metrics, Configuration
from drgpu.node import Node

def work(report: Report, dot_graph_name: str | None, memory_metrics: Memory_Metrics,
         config: Configuration, save_dot: bool = True) -> Node:
    """
    Carry out the analysis and generate the decision tree.
    Args:
        report: The report object.
        dot_graph_name: The name of the dot graph.
        memory_metrics: The memory metrics object.
        config: The configuration object.
        save_dot: Whether to save the dot graph (optional, default is True).
    Returns:
        The decision tree root node.
    """
    analysis = Analysis()
    # {stat_name: stat, } type:{str: Stat}
    all_stats = analysis.all_stats
    if dot_graph_name is None:
        if report.path:
            (_, dot_graph_name) = os.path.split(report.path)
            (dot_graph_name, _) = os.path.splitext(dot_graph_name)
        else:
            dot_graph_name = "drgpu_report"
    # read reports and filter all useful stats
    read_reports.fill_stats(all_stats, report)
    if report.source_report_path or getattr(report, 'source_report_content', None):
        read_reports.fill_source_report(report, analysis)

    hw_tree = Node('Idle')
    hw_tree.suffix_label = ' of total cycles'
    retire_ipc = all_stats.get('retireIPC', None)
    if retire_ipc:
        root_percentage = retire_ipc.value / config.quadrants_per_SM
    else:
        print("Could not get stat retireIPC")
        root_percentage = 0
    hw_tree.percentage = 1 - root_percentage

    hw_tree.prefix_label = read_reports.get_kernel_name(all_stats['kernel_name'].value) + "\n"
    hw_tree.suffix_label = ''
    best_possible = 100 * (
            1.0 - 1.0 / (np.ceil(all_stats['activewarps_per_activecycle'].value
                                 / config.quadrants_per_SM)))
    hw_tree.suffix_label += f" (lowest possible: {int(best_possible)}% for " \
        + f"{int(all_stats['activewarps_per_activecycle'].value)} active warps)"
    max_val = 0
    sol_unit = ""
    for unit in ['SM', 'L1', 'L2', 'Dram', 'Compute_Memory']:
        next_val = all_stats['sol_' + unit.lower()].value
        if next_val > max_val:
            sol_unit = unit
            max_val = next_val
    hw_tree.suffix_label += f"\nUtil/SOL: {max_val:.2f}% ({sol_unit})"

    hw_tree.suffix_label += f"\nIssue IPC: {all_stats['issueIPC'].value:.2f}"

    # first level
    tmpstats = unit_hunt.warp_cant_issue(all_stats)
    gather.add_sub_branch(tmpstats, hw_tree, 1, config)
    if report.source_report_path is not None or getattr(report, 'source_report_content', None):
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
    bottleneck_unit, bottleneck_stats, memory_metrics = \
        unit_hunt.long_scoreboard_throughput(all_stats, memory_metrics, config)
    long_scoreboard_node = gather.find_node(hw_tree, "warp_cant_issue_long_scoreboard")
    latency_stats = unit_hunt.long_scoreboard_latency(all_stats, memory_metrics, config)
    gather.add_sub_branch_for_longscoreboard_latency(latency_stats, long_scoreboard_node, all_stats,
                                                     memory_metrics)
    gather.add_sub_branch_for_longscoreboard_throughput(all_stats, bottleneck_unit,
                                                        bottleneck_stats, long_scoreboard_node, 1,
                                                        config)

    shared_mem_stats = unit_hunt.common_function_pattern(all_stats, r'shared_ld_(\d+)b_executed')
    gather.add_shared_memory_info(all_stats, shared_mem_stats, memory_metrics)
    target_node = gather.find_node(hw_tree, "warp_cant_issue_mio_throttle")
    gather.add_branch_for_mio_throttle(all_stats, shared_mem_stats, memory_metrics, target_node,
                                       config)
    target_node = gather.find_node(hw_tree, "warp_cant_issue_short_scoreboard")
    gather.add_branch_for_short_scoreboard(all_stats, shared_mem_stats, memory_metrics, target_node,
                                           config)

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

    if save_dot:
        dot_graph.build_dot_graph(hw_tree, "dots/" + dot_graph_name)
        print("save to dots/" + dot_graph_name + ".svg")

    return hw_tree


def launch(report: Report, config: Configuration, memory_metrics: Memory_Metrics | None = None,
           output: str | None = None, save_dot: bool = True) -> Node:
    """
    Launch DrGPU with the given arguments.
    Args:
        report: The report data structure populated with report content.
        config: Parsed GPU configuration data.
        memory_metrics: The memory metrics object to update (optional).
        output: Name of the output decision tree file (dot graph name).
        save_dot: Whether to save the dot graph (optional, default is True).
    Returns:
        The decision tree root node.
    """
    if report.kernel_id is None:
        report.kernel_id = 0
    report_path_display = report.path if report.path else "<in-memory>"
    if report.source_report_path:
        source_display = report.source_report_path
    elif getattr(report, 'source_report_content', None) is not None:
        source_display = "<in-memory>"
    else:
        source_display = None
    print(f"Report path: {report_path_display}")
    print(f"Source path: {source_display}")
    if memory_metrics is None:
        memory_metrics = Memory_Metrics()
    hw_tree = work(report, output, memory_metrics, config, save_dot=save_dot)
    return hw_tree


def resolve_memory_config_path(config_arg: str | None) -> Path:
    """
    Resolve the memory config path.
    Args:
        config_arg: The memory config path or name.
    Returns:
        The memory config path.
    """
    base_dir = Path(os.path.dirname(__file__)).parent.absolute()
    if config_arg is None:
        print("You didn't specify running platform for this report. DrGPU will use "
                "gtx1650.ini as the default GPU configuration.")
        return base_dir / 'mem_config' / 'gtx1650.ini'
    config_name = config_arg if config_arg.endswith('.ini') else config_arg + '.ini'
    config_path = Path(config_name)
    if not config_path.is_absolute():
        config_path = base_dir / 'mem_config' / config_name
    return config_path


def get_config_list() -> List[str]:
    """
    Get the list of available config files under the mem_config folder.
    Returns:
        The list of available config files.
    """
    base_dir = Path(os.path.dirname(__file__)).parent.absolute()
    return [os.path.basename(path) for path in (base_dir / 'mem_config').glob('*.ini')]


def load_config(given_config: str) -> Configuration:
    """
    Load the config from the given config name or path.
    Args:
        given_config: The path to the memory config file or a file name in mem_config folder.
    Returns:
        The config.
    """
    memory_config_path = resolve_memory_config_path(given_config)
    if not memory_config_path.exists():
        raise FileNotFoundError(f"Memory config file {memory_config_path} doesn't exist")
    memory_config_content = memory_config_path.read_text(encoding='utf-8')
    config_parser = configparser.ConfigParser()
    config_parser.read_string(memory_config_content)
    config = read_reports.read_config(config_parser, Configuration(),
                                      source_name=str(memory_config_path))
    return config


def load_report(report_path: Path, source_path: Path | None = None,
                kernel_id: int | None = None) -> Report:
    """
    Load the report from the path.
    Args:
        report_path: The path to the report.
        source_path: The path to the source.
        kernel_id: The kernel id.
    Returns:
        The report.
    """
    report_content = report_path.read_text(encoding='utf-8')

    source_content = None
    if source_path is not None:
        source_content = source_path.read_text(encoding='utf-8')

    report = Report(
        path=str(report_path),
        source_report_path=str(source_path) if source_path else None,
        kernel_id=kernel_id if kernel_id is not None else 0,
        report_content=report_content,
        source_report_content=source_content,
    )
    return report
