#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <queue>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

struct Node {
    std::string id;
    std::string parent_id;
    std::string label;
    int parent = -1;
    int root = -1;
    int depth = 0;
    std::uint32_t descendant_count = 0;
    std::vector<int> children;
};

static std::vector<std::string> parse_csv_line(const std::string& line) {
    std::vector<std::string> fields;
    std::string current;
    bool quoted = false;
    for (std::size_t i = 0; i < line.size(); ++i) {
        char ch = line[i];
        if (quoted) {
            if (ch == '"' && i + 1 < line.size() && line[i + 1] == '"') {
                current.push_back('"');
                ++i;
            } else if (ch == '"') {
                quoted = false;
            } else {
                current.push_back(ch);
            }
        } else if (ch == '"') {
            quoted = true;
        } else if (ch == ',') {
            fields.push_back(current);
            current.clear();
        } else {
            current.push_back(ch);
        }
    }
    fields.push_back(current);
    if (!fields.empty() && !fields.back().empty() && fields.back().back() == '\r') {
        fields.back().pop_back();
    }
    return fields;
}

static void write_csv_cell(std::ostream& out, const std::string& value) {
    bool quote = value.find_first_of(",\"\n\r") != std::string::npos;
    if (!quote) {
        out << value;
        return;
    }
    out << '"';
    for (char ch : value) {
        if (ch == '"') out << "\"\"";
        else out << ch;
    }
    out << '"';
}

static std::string join_ids(const std::vector<Node>& nodes, const std::vector<int>& indexes) {
    std::string out;
    for (std::size_t i = 0; i < indexes.size(); ++i) {
        if (i) out.push_back('|');
        out += nodes[indexes[i]].id;
    }
    return out;
}

static int column_index(const std::vector<std::string>& header, const std::string& name) {
    for (std::size_t i = 0; i < header.size(); ++i) {
        if (header[i] == name) return static_cast<int>(i);
    }
    return -1;
}

static std::uint64_t stable_hash(const std::string& value) {
    std::uint64_t h = 1469598103934665603ULL;
    for (unsigned char ch : value) {
        h ^= ch;
        h *= 1099511628211ULL;
    }
    return h;
}

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: annotate_reply_trees INPUT.csv OUTPUT.csv [--root-limit N]\n";
        return 2;
    }
    std::string input_path = argv[1];
    std::string output_path = argv[2];
    std::string root_summary_path;
    std::size_t root_limit = 0;
    for (int i = 3; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--root-limit" && i + 1 < argc) {
            root_limit = static_cast<std::size_t>(std::stoull(argv[++i]));
        } else if (arg == "--root-summary" && i + 1 < argc) {
            root_summary_path = argv[++i];
        }
    }

    std::ifstream input(input_path);
    if (!input) {
        std::cerr << "failed to open input: " << input_path << "\n";
        return 1;
    }

    std::string line;
    if (!std::getline(input, line)) {
        std::cerr << "empty input\n";
        return 1;
    }
    auto header = parse_csv_line(line);
    int node_col = column_index(header, "node_id");
    int parent_col = column_index(header, "parent_node");
    int label_col = column_index(header, "label");
    if (node_col < 0 || parent_col < 0 || label_col < 0) {
        std::cerr << "input must have node_id,parent_node,label columns\n";
        return 1;
    }

    std::vector<Node> nodes;
    nodes.reserve(10'000'000);
    std::unordered_map<std::string, int> id_to_index;
    id_to_index.reserve(10'000'000);

    while (std::getline(input, line)) {
        auto fields = parse_csv_line(line);
        if (static_cast<int>(fields.size()) <= std::max({node_col, parent_col, label_col})) continue;
        if (fields[node_col].empty()) continue;
        int index = static_cast<int>(nodes.size());
        Node node;
        node.id = fields[node_col];
        node.parent_id = fields[parent_col];
        node.label = fields[label_col].empty() ? "general" : fields[label_col];
        nodes.push_back(std::move(node));
        id_to_index.emplace(nodes.back().id, index);
    }

    std::vector<int> roots;
    roots.reserve(nodes.size());
    for (int i = 0; i < static_cast<int>(nodes.size()); ++i) {
        auto it = id_to_index.find(nodes[i].parent_id);
        if (!nodes[i].parent_id.empty() && it != id_to_index.end() && it->second != i) {
            nodes[i].parent = it->second;
            nodes[it->second].children.push_back(i);
        } else {
            roots.push_back(i);
        }
    }

    std::vector<int> bfs_order;
    bfs_order.reserve(nodes.size());
    std::queue<int> queue;
    for (int root : roots) {
        nodes[root].root = root;
        nodes[root].depth = 0;
        queue.push(root);
    }
    while (!queue.empty()) {
        int current = queue.front();
        queue.pop();
        bfs_order.push_back(current);
        for (int child : nodes[current].children) {
            nodes[child].root = nodes[current].root;
            nodes[child].depth = nodes[current].depth + 1;
            queue.push(child);
        }
    }

    for (auto it = bfs_order.rbegin(); it != bfs_order.rend(); ++it) {
        int node = *it;
        std::uint32_t total = 0;
        for (int child : nodes[node].children) {
            total += 1 + nodes[child].descendant_count;
        }
        nodes[node].descendant_count = total;
    }

    std::vector<int> ranked_roots = roots;
    std::sort(ranked_roots.begin(), ranked_roots.end(), [&](int a, int b) {
        if (nodes[a].descendant_count != nodes[b].descendant_count) {
            return nodes[a].descendant_count > nodes[b].descendant_count;
        }
        return stable_hash(nodes[a].id) < stable_hash(nodes[b].id);
    });
    if (root_limit > 0 && ranked_roots.size() > root_limit) ranked_roots.resize(root_limit);

    std::ofstream output(output_path);
    if (!output) {
        std::cerr << "failed to open output: " << output_path << "\n";
        return 1;
    }

    output << "root_rank,node_id,depth,parent_node,children,root_node,root_label,root_children,descendant_count,direct_child_count\n";
    std::size_t written = 0;
    for (std::size_t rank = 0; rank < ranked_roots.size(); ++rank) {
        int root = ranked_roots[rank];
        std::queue<int> write_queue;
        write_queue.push(root);
        while (!write_queue.empty()) {
            int index = write_queue.front();
            write_queue.pop();
            for (int child : nodes[index].children) write_queue.push(child);
            output << (rank + 1) << ',';
            write_csv_cell(output, nodes[index].id);
            output << ',' << nodes[index].depth << ',';
            write_csv_cell(output, nodes[index].parent >= 0 ? nodes[nodes[index].parent].id : "");
            output << ',';
            write_csv_cell(output, join_ids(nodes, nodes[index].children));
            output << ',';
            write_csv_cell(output, nodes[root].id);
            output << ',';
            write_csv_cell(output, nodes[root].label);
            output << ',';
            write_csv_cell(output, join_ids(nodes, nodes[root].children));
            output << ',' << nodes[index].descendant_count << ',' << nodes[index].children.size() << '\n';
            ++written;
        }
    }

    if (!root_summary_path.empty()) {
        std::ofstream root_summary(root_summary_path);
        if (!root_summary) {
            std::cerr << "failed to open root summary: " << root_summary_path << "\n";
            return 1;
        }
        root_summary << "root_rank,root_node,root_label,root_children,descendant_count,direct_child_count\n";
        for (std::size_t rank = 0; rank < ranked_roots.size(); ++rank) {
            int root = ranked_roots[rank];
            root_summary << (rank + 1) << ',';
            write_csv_cell(root_summary, nodes[root].id);
            root_summary << ',';
            write_csv_cell(root_summary, nodes[root].label);
            root_summary << ',';
            write_csv_cell(root_summary, join_ids(nodes, nodes[root].children));
            root_summary << ',' << nodes[root].descendant_count << ',' << nodes[root].children.size() << '\n';
        }
    }

    std::cerr << "read " << nodes.size() << " rows, roots " << roots.size()
              << ", selected roots " << ranked_roots.size()
              << ", wrote " << written << " rows\n";
    return 0;
}
