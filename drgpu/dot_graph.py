from graphviz import Digraph # type: ignore
from drgpu.node import Node, MEMORY_LATENCY_HIERARCHY

colors = [
    "ivory", "aquamarine", "red", "chartreuse", "khaki", "hotpink", "dodgerblue", "gainsboro",
    "skyblue", "wheat", "thistle",
]

def build_dot_graph(hw_tree: Node, dot_file_name: str):
    """Build the dot graph of the stall analysis decision tree via BFS."""
    g = Digraph('hw tree')
    # [(father.name, child), ], have to record their father
    queue = [(hw_tree.name, hw_tree)]
    color_i = 0

    while queue:
        # pop the next node from the queue
        apair = queue.pop(0)
        cur_child: Node = apair[1]
        father_name = apair[0]
        node_shape = 'box'

        node_label = cur_child.get_label()
        node_color = cur_child.get_color()

        # add the node to the graph
        # g.node(name=cur_child.name, label=node_label, style="filled",
        #        color=colors[color_i % len(colors)])
        # g.node(name=cur_child.name, label=node_label, style="filled",
        #        color="/ylgn9/%d" % (9 - color_i%9))
        g.node(name=cur_child.name, label=node_label, style="filled", color=node_color,
               shape=node_shape)
        color_i += 1

        # add the edge connecting the new node to the graph
        if father_name != cur_child.name:
            if (father_name, cur_child.name) in MEMORY_LATENCY_HIERARCHY:
                if father_name == 'avg_latency':
                    edge_label = '='
                else:
                    edge_label  = '+'
                edge_color = 'firebrick'
            else:
                edge_color = 'black'
                edge_label = ''
            g.edge(father_name, cur_child.name, color=edge_color, label=edge_label)

        # add the children of the current node to the queue
        for next_child in cur_child.child:
            queue.append((cur_child.name, next_child))

    g.format = 'svg'
    g.render(dot_file_name, view=False)
