import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("backfill", Path(__file__).parents[1] / "statistics/backfill_sa_target_area.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class BackfillTests(unittest.TestCase):
    def row(self):
        display = dict(alignment_valid=True, viewport_width_css_px=1912,
                       viewport_height_css_px=1076, screen_width_css_px=1912,
                       screen_height_css_px=1076, visual_viewport_scale=1)
        return dict(id=1, task_id="sa", task_type="SA_THREAT_RESPONSE", revision=1,
                    valid_from_us=100, valid_to_us=200, alignment_valid=1,
                    coordinate_space="display_area_normalized", display_json=json.dumps(display),
                    layout_signature="original", regions_json=json.dumps([
                        dict(id="left_candidate_list", shape="rect", visible=True,
                             left=211/1912, right=1011/1912, top=739/1076, bottom=1010/1076)]))

    def test_geometry_and_reject_clipping(self):
        row=self.row()
        r,_=mod.parent_region(row,infer=True)
        self.assertAlmostEqual(r['top'],130/1076)
        self.assertAlmostEqual(r['bottom'],730/1076)
        regions=json.loads(row['regions_json']);regions[0]['right']=1
        row['regions_json']=json.dumps(regions)
        with self.assertRaises(ValueError):mod.parent_region(row,infer=True)

    def test_frames_quality_boundaries_and_legacy(self):
        row=self.row();row['parent'],_=mod.parent_region(row,infer=True)
        for ts,gaze,alignment,expected in [(100,[.3,.3],1,True),(199,[.3,.3],1,True),
                                           (200,[.3,.3],1,False),(120,None,1,False),
                                           (120,[float('nan'),.3],1,False),(120,[.3,.3],0,False),
                                           (120,[.9,.9],1,False)]:
            row['alignment_valid']=alignment
            f=dict(ts_us=ts,gaze=gaze,aoi_revision=1,aoi_hits=['left_ai_target'],hit=True,hits=['legacy'])
            self.assertEqual(mod.patch_frame(f,{1:row}),expected)
            self.assertEqual(f['hits'],['legacy']);self.assertTrue(f['hit'])
            if expected:
                self.assertIn(mod.AOI_ID,f['aoi_hits'])
                self.assertFalse(mod.patch_frame(f,{1:row}))

    def test_explicit_bounds_requires_evidence(self):
        with self.assertRaises(ValueError):
            mod.parent_region(self.row(),dict(left=.1,top=.1,right=.6,bottom=.7))

    def test_copy_preview_repeat_and_missing_raw(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);db=base/'source.db';raw=base/'source_raw';raw.mkdir()
            frame=dict(ts_us=120,gaze=[.3,.3],aoi_revision=1,aoi_hits=[],hit=False)
            (raw/'raw_gaze.jsonl').write_text(json.dumps(frame)+'\n',encoding='utf-8')
            c=sqlite3.connect(db)
            c.execute('CREATE TABLE gaze_tasks(task_id TEXT PRIMARY KEY,data_dir TEXT,end_time_us INTEGER,total_frames INTEGER)')
            c.execute('INSERT INTO gaze_tasks VALUES (?,?,?,?)',('sa',str(raw),200,1))
            row=self.row()
            c.execute('CREATE TABLE gaze_aoi_snapshots ('+','.join(k+(' INTEGER' if isinstance(v,int) else ' TEXT') for k,v in row.items())+')')
            c.execute('INSERT INTO gaze_aoi_snapshots VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
            c.commit();c.close();before=db.read_bytes()
            report=mod.run(db,base/'preview',infer=True)
            self.assertEqual(report['raw_frames'][0]['changed'],1)
            self.assertFalse((base/'preview').exists())
            report=mod.run(db,base/'result',infer=True,apply=True)
            self.assertEqual(db.read_bytes(),before)
            dest=sqlite3.connect(report['output_db'])
            regions=json.loads(dest.execute('select regions_json from gaze_aoi_snapshots').fetchone()[0])
            self.assertEqual(sum(r['id']==mod.AOI_ID for r in regions),1)
            target=Path(dest.execute('select data_dir from gaze_tasks').fetchone()[0])
            self.assertIn(mod.AOI_ID,json.loads((target/'raw_gaze.jsonl').read_text())['aoi_hits'])
            dest.close()
            repeated=mod.run(report['output_db'],None,infer=True)
            self.assertEqual(repeated['snapshots'][0]['action'],'unchanged')
            self.assertEqual(repeated['raw_frames'][0]['changed'],0)
            (raw/'raw_gaze.jsonl').unlink()
            with self.assertRaises(ValueError):mod.run(db,None,infer=True)


if __name__=='__main__':unittest.main()
