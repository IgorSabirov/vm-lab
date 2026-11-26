"""Inventory the publisher's three original workbooks, and cross-check the six Fig. 3a columns.
Run with a directory containing the XLSX files linked under Source Data, Figures 1–3.
"""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import io
import numpy as np
from openpyxl import load_workbook
from pair import FIG3, HERE

def inspect(directory):
    books=[]
    for fig in (1,2,3):
        name=f'41586_2021_3537_MOESM{fig}_ESM.xlsx'
        path=directory/name
        book=load_workbook(path,data_only=False)
        sheets=[]
        for sheet in book:
            data=[r for r in sheet.values if any(c is not None for c in r)]
            sheets.append(dict(name=sheet.title,state=sheet.sheet_state,headers=data[0],
                               nonempty_data_rows=len(data)-1,
                               formula_cells=sum(c.data_type=='f' for row in sheet for c in row)))
        record=dict(name=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),sheets=sheets,
                    url='https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-021-03537-9/MediaObjects/'+name)
        books.append(record)
        if fig!=3: continue
        publisher=np.asarray(list(book['Fig.3a'].values)[1:],dtype=float)
        with ZipFile(HERE.parent/'data'/'cambridge.zip') as z:
            def table(name):
                return np.loadtxt(io.BytesIO(z.read(name)),skiprows=1)
            fast=table(FIG3+'firstSound_redData.txt');slow=table(FIG3+'secondSound_blueData.txt')
        fa=fast[np.argsort(fast[:,0])];sl=slow[np.argsort(slow[:,0])]
        np.testing.assert_allclose(fa[:,:2],sl[:,:2],rtol=0,atol=1e-8)
        delta=np.abs(publisher[np.argsort(publisher[:,0])]-np.column_stack([fa,sl[:,2:]]))
        if delta.shape!=(9,6) or np.max(delta)>1e-8:
            raise ValueError('Cambridge and publisher tables disagree')
        record.update(checked_numeric_cells=delta.size,max_abs_difference=float(delta.max()))
    return dict(workbooks=books,scope='Visible and hidden worksheets including populated cells, all three linked publisher XLSX files.')

if __name__=='__main__':
    args=argparse.ArgumentParser(description=__doc__)
    args.add_argument('directory',type=Path)
    print(json.dumps(inspect(args.parse_args().directory),indent=2,ensure_ascii=False))
