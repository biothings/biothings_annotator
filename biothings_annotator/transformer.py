"""
Different mutation state classes for modifying the state of different annotation responses we
recieve within the biothings annotator
"""

import inspect

import biothings_client


def append_prefix(id, prefix):
    """append prefix to id if not already present to make it a valid Curie ID
    Note that prefix parameter should not include the trailing colon"""
    return f"{prefix}:{id}" if not id.startswith(prefix) else id


class ResponseTransformer:
    def __init__(self, res_by_id, node_type):
        self.res_by_id = res_by_id
        self.node_type = node_type

        self.data_cache = {}  # used to cached required mapping data used for individual transformation
        # typically those data coming from other biothings APIs, we will do a batch
        # query to get them all, and cache them here for later use, to avoid slow
        # one by one queries.

    def _transform_chembl_drug_indications(self, doc):
        if self.node_type != "chem":
            return doc

        def _append_mesh_prefix(chembl):
            xli = chembl.get("drug_indications", [])
            for _doc in xli:
                if "mesh_id" in _doc:
                    # Add MESH prefix to chembl.drug_indications.mesh_id field
                    _doc["mesh_id"] = append_prefix(_doc["mesh_id"], "MESH")

        chembl = doc.get("chembl", {})
        if chembl:
            if isinstance(chembl, list):
                # in case returned chembl is a list, rare but still possible
                for c in chembl:
                    _append_mesh_prefix(c)
            else:
                _append_mesh_prefix(chembl)

        return doc

    def caching_ncit_descriptions(self):
        """cache ncit descriptions for all unii.ncit IDs from self.res_by_id
        deprecated along with _transform_add_ncit_description method.
        """
        ncit_id_list = []
        for res in self.res_by_id.values():
            if isinstance(res, list):
                # in case returned res is a list, rare but still possible
                for r in res:
                    unii = r.get("unii", {})
                    if isinstance(unii, list):
                        for u in unii:
                            ncit = u.get("ncit")
                            if ncit:
                                ncit_id_list.append(ncit)
                    else:
                        ncit = unii.get("ncit")
                        if ncit:
                            ncit_id_list.append(ncit)
            else:
                ncit = res.get("unii", {}).get("ncit")
                if ncit:
                    ncit_id_list.append(ncit)
        if ncit_id_list:
            ncit_api = biothings_client.get_client(url="https://biothings.ncats.io/ncit")
            ncit_id_list = [f"NCIT:{ncit}" for ncit in ncit_id_list]
            ncit_res = ncit_api.getnodes(ncit_id_list, fields="def")
            ncit_def_d = {}
            for hit in ncit_res:
                if hit.get("def"):
                    ncit_def = hit["def"]
                    # remove the trailing " []" if present
                    # delete after data is fixed
                    if ncit_def.startswith('"') and ncit_def.endswith('" []'):
                        ncit_def = ncit_def[1:-4]
                    ncit_def_d[hit["_id"]] = ncit_def
            if ncit_def_d:
                self.data_cache["ncit"] = ncit_def_d

    def deprecated_transform_add_ncit_description(self, doc):
        """
        add ncit_description field to unii object based on unii.ncit field
        deprecated now, as ncit_description is now returned directly from mychem.info
        """
        if self.node_type != "chem":
            return doc

        if "ncit" not in self.data_cache:
            self.caching_ncit_descriptions()

        ncit_def_d = self.data_cache.get("ncit", {})

        def _add_ncit_description(unii):
            ncit = unii.get("ncit")
            ncit = f"NCIT:{ncit}"
            if ncit:
                ncit_def = ncit_def_d.get(ncit)
                if ncit_def:
                    unii["ncit_description"] = ncit_def

        unii = doc.get("unii", {})
        if unii:
            if isinstance(unii, list):
                # in case returned chembl is a list, rare but still possible
                for u in unii:
                    _add_ncit_description(u)
            else:
                _add_ncit_description(unii)
        return doc

    def transform_one_doc(self, doc):
        """transform the response from biothings client"""
        for fn_name, fn in inspect.getmembers(self, predicate=inspect.ismethod):
            if fn_name.startswith("_transform_"):
                if isinstance(doc, list):
                    doc = [fn(r) for r in doc]
                else:
                    doc = fn(doc)
        return doc

    def transform(self):
        for node_id in self.res_by_id:
            res = self.res_by_id[node_id]
            if isinstance(res, list):
                # TODO: handle multiple results here
                res = [self.transform_one_doc(r) for r in res]
            else:
                res = self.transform_one_doc(res)
