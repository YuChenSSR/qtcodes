# -*- coding: utf-8 -*-
"""
Graph decoder for surface codes
"""
import math
from itertools import combinations
from typing import Tuple, List, Dict, Optional, Union, cast
from IPython.display import Image, display

import pydot
import retworkx as rx
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from topological_codes.fitters.base import TopologicalGraphDecoder
from topological_codes.fitters.graph_utils import GraphUtils

TQubit = Tuple[float, float, float]  # (time,row,column) ==> (t,i,j)
TQubitLoc = Tuple[float, float]  # (row,column) ==> (i,j)


class RotatedGraphDecoder(TopologicalGraphDecoder[TQubit]):
    """
    Class to construct the graph corresponding to the possible syndromes
    of a quantum error correction code, and then run suitable decoders.
    """

    def __init__(self, params: Dict) -> None:
        super().__init__(params)
        if "d" not in self.params or "T" not in self.params:
            raise ValueError("Please include d and T in params.")

        self.virtual = self._specify_virtual()
        self.S["X"] = rx.PyGraph(multigraph=False)
        self.S["Z"] = rx.PyGraph(multigraph=False)
        self.node_map: Dict[str, Dict[TQubit, int]] = {"X": {}, "Z": {}}

        self._make_syndrome_graph()

    def _make_syndrome_graph(self) -> None:
        """
        Populates self.S["X"] and self.S["Z"] syndrome rx.PyGraph's with nodes specified by time and position.
        Args:
        Returns:
        """
        start_nodes = {"Z": (0.5, 0.5), "X": (0.5, 1.5)}
        for syndrome_graph_key in ["X", "Z"]:
            # subgraphs for each time step
            for t in range(0, self.params["T"]):
                start_node = start_nodes[syndrome_graph_key]
                node_label = (t,) + start_node
                self.node_map[syndrome_graph_key][node_label] = self.S[
                    syndrome_graph_key
                ].add_node(node_label)
                self._populate_syndrome_graph(
                    (t,) + start_node, t, [], syndrome_graph_key, 1
                )

            # connect physical qubits in same location across subgraphs of adjacent times
            syndrome_nodes_t0 = [
                (t, x, y) for t, x, y in self.S[syndrome_graph_key].nodes() if t == 0
            ]
            for node in syndrome_nodes_t0:
                space_label = (node[1], node[2])
                for t in range(0, self.params["T"] - 1):
                    self.S[syndrome_graph_key].add_edge(
                        self.node_map[syndrome_graph_key][(t,) + space_label],
                        self.node_map[syndrome_graph_key][(t + 1,) + space_label],
                        1,
                    )

    def _specify_virtual(self) -> Dict[str, List[TQubit]]:
        """
        Define coordinates of Z and X virtual syndrome nodes. Our convention is that Z
        virtual syndrome nodes are top/bottom and X virtual nodes are left/right.
        Args:
        Returns:
            virtual (dictionary): where virtual["X"] holds a list of tuples specifying virtual X syndrome nodes
            and equivalently for virtual["Z"]
        """
        virtual: Dict[str, List[TQubit]] = {}
        virtual["X"] = []
        virtual["Z"] = []
        for j in range(0, self.params["d"], 2):
            # Z virtual nodes
            virtual["Z"].append((-1, -0.5, j - 0.5))  # top
            virtual["Z"].append((-1, self.params["d"] - 0.5, j + 0.5))  # bottom

            # X virtual nodes
            virtual["X"].append((-1, j + 0.5, -0.5))  # left
            virtual["X"].append((-1, j - 0.5, self.params["d"] - 0.5))  # right
        return virtual

    def _populate_syndrome_graph(
        self,
        current_node: TQubit,
        t: int,
        visited_nodes: List[TQubit],
        syndrome_graph_key: str,
        edge_weight: int = 1,
    ) -> None:
        """Recursive function to populate syndrome subgraph at time t with syndrome_graph_key X/Z. The current_node
        is connected to neighboring nodes without revisiting a node.

        Args:
            current_node ((t, x, y)): Current syndrome node to be connected with neighboring nodes.
            t (int): Current time, needed if current_node is a virtual node of the form (-1,i,j)
            visited_nodes ([(t, x, y),]): List of syndrome nodes which have already been traver.
            syndrome_graph_key (char): Which X/Z syndrome subgraph these nodes are from.
            edge_weight (float, optional): Weight of edge between two adjacent syndrome nodes. Defaults to 1.

        Returns:
            None: function is to traverse the syndrome nodes and connect neighbors
        """
        visited_nodes.append(current_node)
        neighbors = []
        i = current_node[1]  # syndrome node x coordinate
        j = current_node[2]  # syndrome node y coordinate
        neighbors.append((i - 1, j - 1))  # up left
        neighbors.append((i + 1, j - 1))  # down left
        neighbors.append((i - 1, j + 1))  # up right
        neighbors.append((i + 1, j + 1))  # down right

        normal_neighbors = [
            n
            for n in neighbors
            if self._valid_syndrome(n, syndrome_graph_key)
            and (t, n[0], n[1]) not in visited_nodes
        ]  # syndrome node neighbors of current_node not already visited
        virtual_neighbors = [
            n
            for n in neighbors
            if (-1, n[0], n[1]) in self.virtual[syndrome_graph_key]
            and (-1, n[0], n[1]) not in visited_nodes
        ]  # virtual node neighbors of current_node not already visited

        # no neighbors to add edges
        if not normal_neighbors and not virtual_neighbors:
            return

        # add normal/non-virtual neighbors
        for target in normal_neighbors:
            target_node = (
                t,
            ) + target  # target_node has time t with x and y coordinates from target
            if target_node not in self.S[syndrome_graph_key].nodes():
                # add target_node to syndrome subgraph if it doesn't already exist
                self.node_map[syndrome_graph_key][target_node] = self.S[
                    syndrome_graph_key
                ].add_node(target_node)

            self.S[syndrome_graph_key].add_edge(
                self.node_map[syndrome_graph_key][current_node],
                self.node_map[syndrome_graph_key][target_node],
                edge_weight,
            )  # add edge between current_node and target_node

        # add virtual neighbors
        for target in virtual_neighbors:
            target_node = (
                -1,
            ) + target  # virtual target_node has time -1 with x and y coordinates from target
            if target_node not in self.S[syndrome_graph_key].nodes():
                # add virtual target_node to syndrome subgraph with z coordinate (T-1)/2 for nice plotting, if it doesn't already exist
                self.node_map[syndrome_graph_key][target_node] = self.S[
                    syndrome_graph_key
                ].add_node(target_node)
            self.S[syndrome_graph_key].add_edge(
                self.node_map[syndrome_graph_key][current_node],
                self.node_map[syndrome_graph_key][target_node],
                edge_weight,
            )  # add edge between current_node and virtual target_node

        # recursively traverse normal neighbors
        for target in normal_neighbors:
            self._populate_syndrome_graph(
                (t,) + target, t, visited_nodes, syndrome_graph_key, 1
            )

        # recursively traverse virtual neighbors
        for target in virtual_neighbors:
            self._populate_syndrome_graph(
                (-1,) + target, t, visited_nodes, syndrome_graph_key, 1
            )

    def _valid_syndrome(self, node: TQubitLoc, syndrome_graph_key: str) -> bool:
        """Checks whether a node is a syndrome node under our syndrome_graph_key, which is either X or Z.

        Args:
            node ((t, x, y)): Node in graph.
            syndrome_graph_key (char): Which X/Z syndrome subgraph these nodes are from.

        Returns:
            (bool): whether node is a syndrome node
        """
        i = node[0]
        j = node[1]
        if syndrome_graph_key == "Z":
            if i > 0 and i < self.params["d"] - 1 and j < self.params["d"] and j > -1:
                return True
            else:
                return False
        elif syndrome_graph_key == "X":
            if j > 0 and j < self.params["d"] - 1 and i < self.params["d"] and i > -1:
                return True
            else:
                return False
        else:
            raise ValueError("Please enter a valid syndrome_graph_key: X or Z")

    def _make_error_graph(
        self,
        nodes: List[TQubit],
        syndrome_graph_key: str,
        err_prob: Optional[float] = None,
    ):
        """Creates error syndrome subgraph from list of syndrome nodes. The output of
        this function is a graph that's ready for minimum weight perfect matching (MWPM).

        If err_prob is specified, we adjust the shortest distance between syndrome
        nodes by the degeneracy of the error path.

        Args:
            nodes ([(t, x, y),]): List of changes of syndrome nodes in time.
            syndrome_graph_key (char): Which X/Z syndrome subgraph these nodes are from.
            err_prob (Optional[float]): Probability of IID data qubit X/Z flip. Defaults to None.

        Returns:
            error_graph (rx.PyGraph): Nodes are syndromes, edges are proxy for error probabilities
        """
        node_map: Dict[TQubit, int] = {}
        error_graph = rx.PyGraph(multigraph=False)

        # need to ensure there are an even number of nodes
        make_even = len(nodes) % 2 != 0
        nodes += self.virtual[syndrome_graph_key]

        # add all nodes to error_graph
        for node in nodes:
            if node not in error_graph.nodes():
                node_map[node] = error_graph.add_node(node)

        # Distance is proportional to the probability of this error chain, so
        # finding the maximum-weight perfect matching of the whole graph gives
        # the most likely sequence of errors that led to these syndromes.
        shortest_distance_mat = rx.graph_floyd_warshall_numpy(
            self.S[syndrome_graph_key]
        )

        num_shortest_paths: Dict[int, List[int]] = {}
        for source, target in combinations(nodes, 2):
            if (
                source in self.virtual[syndrome_graph_key]
                and target in self.virtual[syndrome_graph_key]
            ):
                distance = 0.0
            else:
                i = self.node_map[syndrome_graph_key][source]
                j = self.node_map[syndrome_graph_key][target]
                distance = float(shortest_distance_mat[i][j])
                if err_prob:
                    deg, num_shortest_paths = self._path_degeneracy(
                        source,
                        target,
                        syndrome_graph_key,
                        num_shortest_paths,
                        shortest_distance_mat,
                    )
                    distance = distance - math.log(deg) / (
                        math.log1p(-1.0 * err_prob) - math.log(err_prob)
                    )
                distance = -1.0 * distance
            error_graph.add_edge(node_map[source], node_map[target], distance)
        if make_even:
            source = (-1, -1, -1)
            node_map[source] = error_graph.add_node(source)
            for target in self.virtual[syndrome_graph_key]:
                error_graph.add_edge(node_map[source], node_map[target], 0)

        return error_graph

    def _path_degeneracy(
        self,
        a: TQubit,
        b: TQubit,
        syndrome_graph_key: str,
        num_shortest_paths: Dict[int, List[int]],
        shortest_distance_mat: np.ndarray,
    ) -> Tuple[int, Dict[int, List[int]]]:
        """
        Calculate the number of shortest error paths (degeneracy)
        that link two syndrome nodes through both space and time.

        If one of these nodes is virtual this will be stored in target,
        while the other non-virtual node will be stored in source.

        Then, the number of shortest error paths (degeneracy) from source
        to *any* virtual node, which is as equally close to source as source is to target,
        will be added together and returned as the total degeneracy.

        Args:
            a (tuple): Starting or ending syndrome node (degeneracy is symmetric)
            b (tuple): Ending or starting syndrome node (degeneracy is symmetric)
            syndrome_graph_key (str): specifies the syndrome graph ("X" or "Z")
            num_shortest_paths (Dict[int, List[int]]):
                key: source node
                val:
                    val[i] corresponds to number of shortest paths
                    between source node (key) and target node i
                    This saves some computations if already calculated.
            shortest_distance_mat: (np.ndarray):
                shortest_distance_mat[i][j] is the shortest path length
                between node indices i and j

        Returns:
            num (int): Number of degenerate shortest paths matching this syndrome pair
            num_shortest_paths (Dict[int, List[int]]]): updated num_shortest_paths
        """
        a_indx = self.node_map[syndrome_graph_key][a]
        b_indx = self.node_map[syndrome_graph_key][b]

        source = None
        if a[0] == -1:
            target = a_indx  # virtual
            source = b_indx
        elif b[0] == -1:
            target = b_indx  # virtual
            source = a_indx

        if source:
            shortest_distance = shortest_distance_mat[source][target]
            virtual_nodes = self.virtual[syndrome_graph_key]
            total_deg = 0
            for node in virtual_nodes:
                node_indx = self.node_map[syndrome_graph_key][node]
                if shortest_distance_mat[source][node_indx] == shortest_distance:
                    deg, num_shortest_paths = self._path_degeneracy_helper(
                        source, node_indx, syndrome_graph_key, num_shortest_paths
                    )
                    total_deg += deg
        else:
            total_deg, num_shortest_paths = self._path_degeneracy_helper(
                a_indx, b_indx, syndrome_graph_key, num_shortest_paths
            )

        return total_deg, num_shortest_paths

    def _path_degeneracy_helper(
        self,
        a_indx: int,
        b_indx: int,
        syndrome_graph_key: str,
        num_shortest_paths: Dict[int, List[int]],
    ) -> Tuple[int, Dict[int, List[int]]]:
        """Helper to calculate the number of shortest error paths that link two syndrome nodes
        through both space and time.

        Args:
            a_indx (int): Indx of one node
            b_indx (int): Indx of another node
            syndrome_graph_key (str): specifies the syndrome graph ("X" or "Z")
            num_shortest_paths (Dict[int, List[int]]):
                key: source node
                val:
                    val[i] corresponds to number of shortest paths
                    between source node (key) and target node i
                    This saves some computations if already calculated.
        Returns:
            num (int): Number of degenerate shortest paths matching this syndrome pair
            num_shortest_paths (Dict[int, List[int]]]): updated num_shortest_paths
        """
        if a_indx in num_shortest_paths.keys():
            return num_shortest_paths[a_indx][b_indx], num_shortest_paths
        elif b_indx in num_shortest_paths.keys():
            return num_shortest_paths[b_indx][a_indx], num_shortest_paths
        else:
            num_shortest_paths[a_indx] = GraphUtils.num_shortest_paths(
                self.S[syndrome_graph_key], a_indx
            )
            return num_shortest_paths[a_indx][b_indx], num_shortest_paths

    def _run_mwpm_graph(
        self, matching_graph: rx.PyGraph, floats: bool = False
    ) -> rx.PyGraph:
        """
        Return matches of minimum weight perfect matching (MWPM) on matching_graph.
        This method is only to be used in tutorials to demo the matched graph.

        Args:
            matching_graph (rx.PyGraph): Graph to run MWPM.
            floats (bool):
                whether or not the graph contains float edge weights

        Returns:
            matched_graph (rx.PyGraph): matched graph without virtual-virtual matches
        """

        # TODO: Temporary fix for matching with float edge weights
        weight_fn = int if not floats else lambda n: int(n * 10000)
        matches_idxs = rx.max_weight_matching(
            matching_graph, max_cardinality=True, weight_fn=weight_fn,
        )
        filtered_matches_idxs = [
            (i, j)
            for (i, j) in matches_idxs
            if not (matching_graph[i][0] == -1 and matching_graph[j][0] == -1)
        ]

        matched_graph = rx.PyGraph(multigraph=False)
        node_map = {}
        for i, j in filtered_matches_idxs:
            weight = matching_graph.get_edge_data(i, j)
            for node in [i, j]:
                if matching_graph[node] not in matched_graph.nodes():
                    node_map[matching_graph[node]] = matched_graph.add_node(
                        matching_graph[node]
                    )
            matched_graph.add_edge(
                node_map[matching_graph[i]], node_map[matching_graph[j]], weight
            )
        return matched_graph

    def _run_mwpm(
        self, matching_graph: rx.PyGraph, floats=False
    ) -> List[Tuple[TQubit, TQubit]]:
        """
        Return matches of minimum weight perfect matching (MWPM) on matching_graph.

        Args:
            matching_graph (rx.PyGraph): Graph to run MWPM.
            floats (bool):
                whether or not the graph contains float edge weights

        Returns:
            [(node, node),]: List of matchings found from MWPM
        """
        # TODO: Temporary fix for matching with float edge weights
        weight_fn = int if not floats else lambda n: int(n * 10000)
        matches_idxs = rx.max_weight_matching(
            matching_graph, max_cardinality=True, weight_fn=weight_fn,
        )
        matches = [(matching_graph[i], matching_graph[j]) for (i, j) in matches_idxs]
        filtered_matches = [
            (source, target)
            for (source, target) in matches
            if not (source[0] == -1 and target[0] == -1)
        ]

        return filtered_matches

    def _corrections(
        self,
        syndromes: List[TQubit],
        syndrome_graph_key: str,
        err_prob: Optional[float] = None,
    ) -> List[Tuple[TQubit, TQubit]]:
        """
        Args:
            syndromes ({str,[node,]}):
                key: syndrome_graph_key, either "X", "Z"
                value: activated syndrome nodes (t,i,j)

                Dictionary with syndromes["X"] containing tuples of the form
                (t,i,j) where t specifies time and (i,j) specify position of
                the X syndrome node changed from its value at (t-1,i,j),
                and similarly, syndromes["Z"] for Z syndrome nodes.

        Returns:
            net_flips ({(i,j):np.ndarray}):
                dictionary with key representing physical (data) qubit
                and value representing the net error matrix on that data qubit.
                e.g. key: (0,0), value: [[0,1],[1,0]] (X error)

        Additional Information:
            This method can be used to correct readout errors as shown in self.correct_readout.
        """
        if not syndromes:
            return []

        error_graph = self._make_error_graph(
            syndromes, syndrome_graph_key, err_prob=err_prob
        )
        matches = self._run_mwpm(error_graph, floats=err_prob is not None)
        return matches

    def correct_readout(
        self,
        syndromes: Union[str, Dict[str, List[TQubit]]],
        logical_qubit_value: Optional[int] = None,
        logical_readout_type: str = "Z",
        err_prob: Optional[float] = None,
    ) -> int:
        """
        Args:
            syndromes (Union[str, Dict[str, List[TQubit]]]): either...
                (Dict[str, List[TQubit]]]):
                    key: syndrome type
                    value: (time, row, col) of parsed syndrome hits (changes between consecutive rounds)
                (str): string like "1 00000000 00000000" representing "R S2 S1" (d=3, T=2) where
                S1 is the first set of changed syndrome nodes (XOR'd with quiescent state syndrome measurements)
                S1 has the form: X3X2X1X0Z3Z2Z1Z0 in the case of d = 3. R represents the logical Z readout result.
            logical_qubit_value (Optional[int]): measured logical qubit value
            logical_readout_type (str): logical readout type out of "X" or "Z"
            err_prob (Optional[float]): Probability of IID data qubit X/Z flip. Defaults to None.
        Returns:
            logical_qubit_value (int): The most probable encoded value of the logical qubit.
        Additional Information:
            This method can be used to benchmark logical error rates, as well as perform fault tolerant readout.
        """
        if type(syndromes) == str:
            logical_qubit_value, syndromes = self._string2nodes(str(syndromes))
        syndromes = cast(Dict[str, List[TQubit]], syndromes)
        logical_qubit_value = cast(int, logical_qubit_value)

        matches = self._corrections(
            syndromes[logical_readout_type], logical_readout_type, err_prob=err_prob
        )

        for match in matches:
            if self._is_crossing_readout_path(match, logical_readout_type):
                logical_qubit_value = (logical_qubit_value + 1) % 2
        return logical_qubit_value

    def _is_crossing_readout_path(
        self, match: Tuple[TQubit, TQubit], logical_readout_type: str
    ) -> bool:
        """
        Helper method that detects whether the match is crossing the readout path.

        Args:
            match (Tuple[TQubit, TQubit]): match in MWPM between two nodes
            logical_readout_type (str): "X" or "Z"

        Returns:
            (bool): whether or not the match is crosing the readout path
        """

        # TODO Logical Z readout will be performed with data qubits in the top row,
        # this can be generalized later

        source, target = match
        if logical_readout_type == "Z":
            return (source[0] == -1 and source[1] == -0.5) or (
                target[0] == -1 and target[1] == -0.5
            )  # top
        elif logical_readout_type == "X":
            return (source[0] == -1 and source[2] == -0.5) or (
                target[0] == -1 and target[2] == -0.5
            )  # left
        else:
            raise ValueError("Please enter a valid logical_readout_type (X/Z).")

    def _string2nodes(self, readout_string: str) -> Tuple[int, Dict[str, List[TQubit]]]:
        """
        Converts readout string to readout nodes.

        Turns a readout string (e.g. 1 10100000 10010000) into an
        appropriate logical readout value and XOR-ed syndrome locations
        according to our grid coordinate convention.

        Args:
            readout_string (str):
                Readout of the form "0 00000000 00000000" (logical_readout syndrome_1 syndrome_0)
                or of the form "000000000 00000000 00000000" (lattice_readout syndrome_1 syndrome_0)

        Returns:
            logical_readout (int):
                logical readout value
            syndromes (Dict[str, List[TQubit]]]):
                key: syndrome type
                value: (time, row, col) of parsed syndrome hits (changes between consecutive rounds)
        """
        #  TODO: This duplicates the logic in parse_readout. Consolidate into a mixin util.

        d = self.params["d"]
        num_syn = (d ** 2 - 1) // 2
        chunks = readout_string.split(" ")

        logical_readout = int(chunks[0])
        chunks = chunks[1:]

        int_syndromes = [int(x, base=2) for x in chunks[::-1]]
        xor_syndromes = [a ^ b for (a, b) in zip(int_syndromes, int_syndromes[1:])]

        mask_z = "1" * num_syn
        mask_x = mask_z + "0" * num_syn
        x_syndromes = [(x & int(mask_x, base=2)) >> num_syn for x in xor_syndromes]
        z_syndromes = [x & int(mask_z, base=2) for x in xor_syndromes]

        X = []
        per_row_x = d // 2
        for T, syndrome in enumerate(x_syndromes):
            for loc in range(num_syn):
                if syndrome & 1 << loc:
                    row = -0.5 + loc // per_row_x
                    col = (0.5 + (loc // per_row_x) % 2) + (loc % per_row_x) * 2
                    X.append((float(T), row, col))

        Z = []
        per_row_z = d // 2 + 1
        for T, syndrome in enumerate(z_syndromes):
            for loc in range(num_syn):
                if syndrome & 1 << loc:
                    row = 0.5 + loc // per_row_z
                    col = (0.5 - (loc // per_row_z) % 2) + (loc % per_row_z) * 2
                    Z.append((float(T), row, col))

        return (
            logical_readout,
            {"X": X, "Z": Z,},
        )

    def draw(self, graph: rx.PyGraph) -> None:
        """
        Plots 2D graphs in IPython/Jupyter.

        Args:
            graph (rx.PyGraph): graph to be plotted
        """
        if self.params["T"] > 1:
            self.draw3D(graph)
            return
        pdot = pydot.graph_from_dot_data(
            graph.to_dot(
                edge_attr=lambda e: {
                    "label": str(round(float(e), 3)),
                    "fontsize": "8",
                },
                node_attr=lambda n: {
                    "label": str(n),
                    "pos": f'"{n[2]},{-1.0*n[1]}!"',
                    "fontsize": "8",
                    "color": "black",
                    "fillcolor": "lightblue",
                    "style": "filled",
                },
                graph_attr={"outputorder": "edgesfirst"},
            )
        )[0]
        plt_image = Image(pdot.create_png(prog="fdp"))
        display(plt_image)

    def draw3D(self, graph: rx.PyGraph, angle: Optional[List[float]] = None) -> None:
        """Plots a graph with edge labels in 3D.

        Args:
            G (rx.PyGraph): Graph to be plotted in 3D.
            angle ([float, float]): Initial 3D angle view. Defaults to [-116, 22]

        Returns:
            None: Plot is displayed in plt.show()
        """

        angle = [-116, 22] if not angle else angle
        # Define color range based on time
        colors = {
            node: plt.cm.plasma((node[0] + 1) / self.params["T"])
            for node in graph.nodes()
        }

        def node_to_pos3D(node):
            z = (self.params["T"] - 1.0) / 2.0 if node[0] == -1 else node[0]
            return node[2], -node[1], z

        # 3D network plot
        with plt.style.context(("ggplot")):
            fig = plt.figure(figsize=(20, 14))
            ax = Axes3D(fig)

            # Loop on the nodes and look up in pos dictionary to extract the x,y,z coordinates of each node
            for node in graph.nodes():
                xi, yi, zi = node_to_pos3D(node)

                # Scatter plot
                ax.scatter(
                    xi,
                    yi,
                    zi,
                    color=colors[node],
                    s=120 * 1,
                    edgecolors="k",
                    alpha=0.7,
                )

                # Label node position
                ax.text(xi, yi, zi, node, fontsize=20)

            # Loop on the edges to get the x,y,z, coordinates of the connected nodes
            # Those two points are the extrema of the line to be plotted
            for src, tgt in graph.edge_list():
                x_1, y_1, z_1 = node_to_pos3D(graph[src])
                x_2, y_2, z_2 = node_to_pos3D(graph[tgt])

                x_line = np.array((x_1, x_2))
                y_line = np.array((y_1, y_2))
                z_line = np.array((z_1, z_2))

                # Plot the connecting lines
                ax.plot(x_line, y_line, z_line, color="black", alpha=0.5)

                # Label edges at midpoints
                x_mid = (x_1 + x_2) / 2
                y_mid = (y_1 + y_2) / 2
                z_mid = (z_1 + z_2) / 2
                label = round(graph.get_edge_data(src, tgt), 2)
                ax.text(x_mid, y_mid, z_mid, label, fontsize=14)

        # Set the initial view
        ax.view_init(angle[1], angle[0])

        # Hide the axes
        ax.set_axis_off()

        # Get rid of colored axes planes
        # First remove fill
        ax.xaxis.pane.fill = False
        ax.yaxis.pane.fill = False
        ax.zaxis.pane.fill = False

        # Now set color to white (or whatever is "invisible")
        ax.xaxis.pane.set_edgecolor("w")
        ax.yaxis.pane.set_edgecolor("w")
        ax.zaxis.pane.set_edgecolor("w")

        plt.show()