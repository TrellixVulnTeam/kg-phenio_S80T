"""Provide utilities for aiding transformations."""
import gzip
import logging
import os
import re
import shutil
import zipfile
from typing import Any, Dict, List, Union

from tqdm import tqdm  # type: ignore


class TransformError(Exception):
    """Base class for other exceptions."""

    pass


class ItemInDictNotFoundError(TransformError):
    """Raised when the input value is too small."""

    pass


# TODO: option to further refine typing of method arguments below.


def multi_page_table_to_list(multi_page_table: Any) -> List[Dict]:
    """Return table data returned from tabula.io.read_pdf().

    Possibly broken over several pages, into a list
    of dicts, one dict for each row.
    Args:
        multi_page_table:

    Returns:
        table_data: A list of dicts, where each dict is item from one row.
    """
    # iterate through data for each of 3 pages
    table_data: List[Dict] = []

    header_items = get_header_items(multi_page_table[0])

    for this_page in multi_page_table:
        for row in this_page["data"]:
            if len(row) != 4:
                logging.warning("Unexpected number of rows in {}".format(row))

            items = [d["text"] for d in row]
            this_dict = dict(zip(header_items, items))
            table_data.append(this_dict)

    return table_data


def get_header_items(table_data: Any) -> List:
    """Get header from (first page of) a table.

    Args:
        table_data: Data, as list of dicts from tabula.io.read_pdf().

    Returns:
        header_items: An array of header items.
    """
    header = table_data["data"].pop(0)
    header_items = [d["text"] for d in header]

    return header_items


def write_node_edge_item(fh: Any, header: List, data: List, sep: str = r"""\t"""):
    r"""Write out a single line for a node or an edge in *.tsv.

    :param fh: file handle of node or edge file
    :param header: list of header items
    :param data: data for line to write out
    :param sep: separator [\t]
    """
    if len(header) != len(data):
        raise Exception("Header and data are not the same length.")
    try:
        fh.write(sep.join(data) + "\n")
    except IOError:
        logging.warning("Can't write data for {}".format(data))


def get_item_by_priority(items_dict: dict, keys_by_priority: list) -> str:
    """Retrieve item from a dict using a list of keys.

    In descending order of priority.
    :param items_dict:
    :param keys_by_priority: list of keys to use to find values
    :return: str: first value in dict for first item in keys_by_priority
    that isn't blank, or None
    """
    value = None
    for key in keys_by_priority:
        if key in items_dict and items_dict[key] != "":
            value = items_dict[key]
            break
    if value is None:
        raise ItemInDictNotFoundError("Can't find item in items_dict {}"
                                      .format(items_dict))
    return value


def data_to_dict(these_keys, these_values) -> dict:
    """Zip up two lists to make a dict.

    :param these_keys: keys for new dict
    :param these_values: values for new dict
    :return: dictionary
    """
    return dict(zip(these_keys, these_values))


def uniprot_make_name_to_id_mapping(dat_gz_file: str) -> dict:
    """Make dict with name to id mapping from Uniprot dat.gz file.

    Example:
    ftp://ftp.uniprot.org/pub/databases/uniprot/current_release/
    knowledgebase/idmapping/by_organism/HUMAN_9606_idmapping.dat.gz
    :param dat_gz_file:
    :return: dict with mapping
    """
    name_to_id_map = dict()
    logging.info("Making uniprot name to id map")
    with gzip.open(dat_gz_file, mode="rb") as file:
        for line in tqdm(file):
            items = line.decode().strip().split("\t")
            name_to_id_map[items[2]] = items[0]
    return name_to_id_map


def uniprot_name_to_id(name_to_id_map: dict, name: str) -> Union[str, None]:
    """Map Uniprot name to ID.

    :param name_to_id_map: mapping dict[name] -> id
    :param name: name
    :return: id string, or None
    """
    if name in name_to_id_map:
        return name_to_id_map[name]
    else:
        return None


def parse_header(header_string: str, sep: str = "\t") -> List:
    """Parse header data.

    Args:
        header_string: A string containing header items.
        sep: A string containing a delimiter.
    Returns:
        A list of header items.
    """
    header = header_string.strip().split(sep)
    return [i.replace('"', "") for i in header]


def parse_line(this_line: str, header_items: List, sep=",") -> Dict:
    """Process a line of text from the csv file.

    Args:
        this_line: A string containing a line of text.
        header_items: A list of header items.
        sep: A string containing a delimiter.

    Returns:
        item_dict: A dictionary of header items and a processed item from the dataset.
    """
    data = this_line.strip().split(sep)
    data = [i.replace('"', "") for i in data]

    item_dict = data_to_dict(header_items, data)

    return item_dict


def unzip_to_tempdir(zip_file_name: str, tempdir: str) -> None:
    """Unzip a zip file to a temp directory."""
    with zipfile.ZipFile(zip_file_name, "r") as z:
        z.extractall(tempdir)


def ungzip_to_tempdir(gzipped_file: str, tempdir: str) -> str:
    """Unzip a gzip file to a temp directory."""
    ungzipped_file = os.path.join(tempdir, os.path.basename(gzipped_file))
    if ungzipped_file.endswith(".gz"):
        ungzipped_file = os.path.splitext(ungzipped_file)[0]

    with gzip.open(gzipped_file, "rb") as f_in, open(ungzipped_file, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return ungzipped_file


def guess_bl_category(identifier: str) -> str:
    """Guess category for a given identifier.

    Note: This is a temporary solution and should not be used long term.
    Args:
        identifier: A CURIE
    Returns:
        The category for the given CURIE
    """
    prefix = identifier.split(":")[0]
    if prefix in {"UniProtKB", "ComplexPortal"}:
        category = "biolink:Protein"
    elif prefix in {"GO"}:
        category = "biolink:OntologyClass"
    else:
        category = "biolink:NamedThing"
    return category


def collapse_uniprot_curie(uniprot_curie: str) -> str:
    """Collapse protein entry to parent protein from a UniProtKB curie.

    For an isoform such as UniprotKB:P63151-1
    or UniprotKB:P63151-2, collapse to parent protein
    (UniprotKB:P63151 / UniprotKB:P63151).
    :param uniprot_curie:
    :return: collapsed UniProtKB ID
    """
    if re.match(r"^uniprotkb:", uniprot_curie, re.IGNORECASE):
        uniprot_curie = re.sub(r"\-\d+$", "", uniprot_curie)
    return uniprot_curie


def remove_obsoletes(nodepath: str, edgepath: str) -> None:
    """
    Remove obsolete nodes and related edges.

    Given a tuple of paths to a graph nodefile and edgefile,
    both in KGX tsv, removes those nodes and their involved
    edges where nodes are obsolete. Obsolete status is determined
    by matching at least one of the following conditions:
    1. 'name' field begins with the word 'obsolete'
    2. First node participates in a 'IAO:0100001' edge ("term replaced by")
    3. First node participates in an edge with 'OIO:ObsoleteClass' as the object
    This makes some assumptions about which column contains the node name field.

    :param nodepath: str, path to the node file
    :param edgepath: str, path to the edge file
    """
    outnodepath = nodepath + ".tmp"
    outedgepath = edgepath + ".tmp"

    obsolete_nodes = []

    try:
        with open(nodepath, "r") as innodefile, open(edgepath, "r") as inedgefile:
            with open(outnodepath, "w") as outnodefile, open(
                outedgepath, "w"
            ) as outedgefile:
                for line in innodefile:
                    line_split = (line.rstrip()).split("\t")
                    if (line_split[2].lower()).startswith("obsolete"):
                        # collect the obsolete node ID so we
                        # can remove its edges too
                        obsolete_nodes.append(line_split[0])
                        continue
                for line in inedgefile:
                    line_split = (line.rstrip()).split("\t")
                    if (
                        line_split[1] in obsolete_nodes
                        or line_split[3] in obsolete_nodes
                    ):
                        continue
                    elif (
                        line_split[5] == "IAO:0100001"
                        or line_split[3] == "OIO:ObsoleteClass"
                    ):
                        obsolete_nodes.append(line_split[1])
                        continue
                    else:
                        outedgefile.write("\t".join(line_split) + "\n")
                # Iterate over the nodefile one more time,
                # in case the edges told us anything new
                innodefile.seek(0)
                for line in innodefile:
                    line_split = (line.rstrip()).split("\t")
                    if line_split[0] in obsolete_nodes:
                        continue
                    else:
                        outnodefile.write("\t".join(line_split) + "\n")
        os.replace(outnodepath, nodepath)
        os.replace(outedgepath, edgepath)
    except (IOError, KeyError) as e:
        print(f"Failed to remove obsoletes from {nodepath} and {edgepath}: {e}")
