# Copyright (c) 2020 Intel Corporation. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sub license, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice (including the
# next paragraph) shall be included in all copies or substantial portions
# of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NON-INFRINGEMENT.
# IN NO EVENT SHALL PRECISION INSIGHT AND/OR ITS SUPPLIERS BE LIABLE FOR
# ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import csv
import os
import shutil
import tempfile
import unittest
import zipfile
from datetime import datetime

from decoder.fpt_and_cdt_utilities import find_fpt_in_opened_file, get_all_cdt, CodePartitionDescriptor, \
    get_code_objects_in_code_partition, get_huffman_compressed_code_objects_in_code_partition


def print_info(archive_name):
    zf = zipfile.ZipFile(archive_name)
    print_info_zip(zf)


def print_info_zip(zf):
    for info in zf.infolist():
        print(info.filename)
        print('\tComment:\t', info.comment)
        print('\tModified:\t', datetime(*info.date_time))
        print('\tSystem:\t\t', info.create_system, '(0 = Windows, 3 = Unix)')
        print('\tZIP version:\t', info.create_version)
        print('\tCompressed:\t', info.compress_size, 'bytes')
        print('\tUncompressed:\t', info.file_size, 'bytes')
        print()


class FileTableTests(unittest.TestCase):
    file_input_v11 = None
    file_input_v12 = None

    @classmethod
    def setUpClass(cls):
        # open a fresh handle to v11 and v12 test files
        source_file_v11 = zipfile.ZipFile("../test_resources/SPT_C0_CORP_SI_REL (v11).zip")
        source_file_v12 = zipfile.ZipFile("../test_resources/CMP_LP_A0_FW_CORP_SILICON_REL (v12).zip")
        src = source_file_v11.open("SPT_C0_CORP_SI_REL/cse_image.bin")
        # unzip to temp file
        cls.file_input_v11 = tempfile.NamedTemporaryFile()
        shutil.copyfileobj(src, cls.file_input_v11)
        # rewind the temp file
        cls.file_input_v11.seek(0, os.SEEK_SET)

        src = source_file_v12.open("fw/bin/CML_CMP_LP_A0_CORP_SI_REL/cse_image.bin")
        # unzip to temp file
        cls.file_input_v12 = tempfile.NamedTemporaryFile()
        shutil.copyfileobj(src, cls.file_input_v12)
        # rewind the temp file
        cls.file_input_v12.seek(0, os.SEEK_SET)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.file_input_v11.close()
        except:
            pass
        try:
            cls.file_input_v12.close()
        except:
            pass

    def setUp(self) -> None:
        # rewind both temp files
        FileTableTests.file_input_v11.seek(0, os.SEEK_SET)
        FileTableTests.file_input_v12.seek(0, os.SEEK_SET)

    def test_locate_file_table(self):
        with self.subTest(file_input_object="v11"):
            found_positions = self._locate_file_table_positions(FileTableTests.file_input_v11.file)
            self.assertEqual(len(found_positions), 1, "only 1 file table (position) should be found")
            fpt_info = found_positions[0]
            self.assertEqual(fpt_info[0], 0x10, "file table starts at offset 0x10")
            self.assertEqual(fpt_info[1], 13, "file table contains exactly 13 entries")
            self.assertEqual(fpt_info[2], 0x20, "file table header version is == 0x20")
            self.assertEqual(fpt_info[3], 0x10, "file table entry (header) version is == 0x10")

        with self.subTest(file_input_object="v12"):
            found_positions = self._locate_file_table_positions(FileTableTests.file_input_v12.file)
            self.assertEqual(len(found_positions), 1, "only 1 file table (position) should be found")
            fpt_info = found_positions[0]
            self.assertEqual(fpt_info[0], 0x10, "file table starts at offset 0x10")
            self.assertEqual(fpt_info[1], 17, "file table contains exactly 13 entries")
            self.assertEqual(fpt_info[2], 0x20, "file table header version is == 0x20")
            self.assertEqual(fpt_info[3], 0x10, "file table entry (header) version is == 0x10")

    @staticmethod
    def _locate_file_table_positions(file_input_object):
        # start at the beginning of the file
        found_positions = []
        found_position = find_fpt_in_opened_file(file_input_object, 0)
        while found_position:
            found_positions.append(found_position)
            found_position = find_fpt_in_opened_file(file_input_object, found_position[0] + 1)
        return found_positions

    v11_code_partition_test_answers = {
        'FTPR': [1241088, 4096],
        'FTUP': [3727360, 2564096],
        'DLMP': [12288, 1236992],
        'NFTP': [3190784, 2564096],
        'WCOD': [524288, 5754880],
        'LOCL': [12288, 6279168],
        'ISHC': [200704, 6303744]
    }

    v12_code_partition_test_answers = {
        'FTPR': [1228800, 4096],
        'FTUP': [5140480, 2621440],
        'NFTP': [3862528, 2621440],
        'RBEP': [65536, 2535424],
        'WCOD': [1261568, 6483968],
        'LOCL': [16384, 7745536],
    }

    def test_get_all_code_partition_descriptors_via_file_table(self):
        with self.subTest(file_input_object="v11"):
            code_partition_descriptors = get_all_cdt(FileTableTests.file_input_v11.file, 0x10)
            self.assertIsNotNone(code_partition_descriptors, "input file contains code partitions")
            self._check_code_partitions_names(code_partition_descriptors,
                                              FileTableTests.v11_code_partition_test_answers.keys())
            self._check_code_partition_size_and_offset(code_partition_descriptors,
                                                       FileTableTests.v11_code_partition_test_answers)

        print("v12")
        with self.subTest(file_input_object="v12"):
            code_partition_descriptors = get_all_cdt(FileTableTests.file_input_v12.file, 0x10)
            self.assertIsNotNone(code_partition_descriptors, "input file contains code partitions")
            self._check_code_partitions_names(code_partition_descriptors,
                                              FileTableTests.v12_code_partition_test_answers.keys())
            self._check_code_partition_size_and_offset(code_partition_descriptors,
                                                       FileTableTests.v12_code_partition_test_answers)

    def _check_code_partitions_names(self, descriptors: CodePartitionDescriptor, check_set):
        nameset = set()
        for cpd in descriptors:
            nameset.add(cpd.name)
        missing_set = check_set - nameset
        mstr = ",".join(missing_set)
        self.assertTrue(len(missing_set) == 0, mstr + " partition(s) should be present in the input file")
        extra_set = nameset - check_set
        mstr = ",".join(extra_set)
        self.assertTrue(len(extra_set) == 0, mstr + " partition(s) should NOT be present in the input file")

    def _check_code_partition_size_and_offset(self, descriptors: CodePartitionDescriptor, check_dictionary):
        for cpd in descriptors:
            size_and_offset = check_dictionary.get(cpd.name)
            self.assertIsNotNone(size_and_offset, "input file should NOT contain a code partition named {}"
                                 .format(cpd.name))
            self.assertEqual(cpd.size, size_and_offset[0], "{0} partition should be of size {1} (was {2} instead)"
                             .format(cpd.name, size_and_offset[0], cpd.size)
                             )
            self.assertEqual(cpd.offset_of_cdt_header, size_and_offset[1],
                             "{0} partition should be of size {1} (was {2} instead)"
                             .format(cpd.name, size_and_offset[1], cpd.offset_of_cdt_header)
                             )

    def test_get_all_code_objects_in_code_partition(self):
        with self.subTest(file_input_object="v11"):
            # FileTableTests.file_input_v11.file   "../test_resources/code_object_entries_v11.csv"
            self._test_get_all_code_objects_in_code_partition(FileTableTests.file_input_v11.file,
                                                              "../test_resources/code_object_entries_v11.csv",
                                                              False)
            self._test_get_all_code_objects_in_code_partition(FileTableTests.file_input_v11.file,
                                                              "../test_resources/code_object_entries_v11.csv",
                                                              True)

    def _test_get_all_code_objects_in_code_partition(self,
                                                     file_input, truth_csv_file_fqpn,
                                                     only_huffman_compressed: bool):
        code_partition_descriptors = get_all_cdt(file_input, 0x10)
        self.assertIsNotNone(code_partition_descriptors, "input file contains code partitions")

        chosen_cpd: CodePartitionDescriptor = None
        # TEST PARTITION *WITH* CODE OBJECTS
        # find the FTPR code partition object (it is known to contain code object entries)
        for cpd in code_partition_descriptors:
            if cpd.name == "FTPR":
                chosen_cpd = cpd
                break
        self.assertIsNotNone(chosen_cpd, "code partition named 'FTPR' should exist in input file")
        if only_huffman_compressed:
            code_objects_in_partition = \
                get_huffman_compressed_code_objects_in_code_partition(file_input, chosen_cpd)
        else:
            code_objects_in_partition = get_code_objects_in_code_partition(file_input, chosen_cpd)
        returned_code_object_info = {}
        true_code_object_infos = {}
        for code_object_entry in code_objects_in_partition:
            returned_code_object_info[code_object_entry.name] = code_object_entry
        with open(truth_csv_file_fqpn, newline='') as cvsfile:
            reader = csv.reader(cvsfile)
            for partition_name, object_name, relative_offset, size, encoded in reader:
                if partition_name != chosen_cpd.name:
                    continue
                true_code_object_infos[object_name] = [int(relative_offset), int(size),
                                                       (True if encoded == "True" else False)]
        self._check_code_object_information(returned_code_object_info, true_code_object_infos,
                                            only_huffman_compressed)

    def _check_code_object_information(self, candidate_code_object_infos, true_code_object_infos,
                                       only_huffman_compressed: bool):
        if only_huffman_compressed:
            # filter out the true_code_object_infos that aren't huffman compressed = True
            true_code_object_infos = dict(filter(lambda e: e[1][2] is True, true_code_object_infos.items()))
        missing_nameset = true_code_object_infos.keys() - candidate_code_object_infos.keys()
        mstr = ",".join(missing_nameset)
        self.assertTrue(len(missing_nameset) == 0,
                        mstr + " code objects should be present in the input file")
        extra_nameset = candidate_code_object_infos.keys() - true_code_object_infos.keys()
        mstr = ",".join(extra_nameset)
        self.assertTrue(len(extra_nameset) == 0, mstr + " code objects should NOT be present in the input file")

        # code object infos: [0] offset , [1] size , [2] huffman encoded? (True|False)
        for code_object_name, code_object_info in candidate_code_object_infos.items():
            true_code_object_info = true_code_object_infos.get(code_object_name)
            self.assertIsNotNone(code_object_name, "code object named {} should NOT be present in the input file"
                                 .format(code_object_name)
                                 )
            self.assertEqual(code_object_info.getoffset(), true_code_object_info[0],
                             "code object {0} should be at relative "
                             "offset {1} (was {2} instead)"
                             .format(code_object_name, true_code_object_info[0], code_object_info.getoffset())
                             )
            self.assertEqual(code_object_info.getsize(), true_code_object_info[1], "code object {0} should be size "
                                                                                   "{1} (was {2} instead)"
                             .format(code_object_name, true_code_object_info[1], code_object_info.getsize())
                             )
            self.assertEqual(code_object_info.getishuffmancompressed(), true_code_object_info[2],
                             "code object {0} should be denoted as Huffman-encoded = {1} (was {2} instead)"
                             .format(code_object_name, true_code_object_info[2],
                                     code_object_info.getishuffmancompressed())
                             )


if __name__ == '__main__':
    unittest.main()
