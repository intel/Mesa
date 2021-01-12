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

import filecmp
import os
import shutil
import tempfile
import unittest
import zipfile

from decoder.csme_unpack import main_run_for_packaged_compressed_file_input, read_ascii_huffman_table_from_file, \
    clear_huffman_table_data, get_huffman_table


class CSMEDecodeTests(unittest.TestCase):
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
        CSMEDecodeTests.file_input_v11.seek(0, os.SEEK_SET)
        CSMEDecodeTests.file_input_v12.seek(0, os.SEEK_SET)
        clear_huffman_table_data()

    def test_decode_single_code_object(self):
        with tempfile.TemporaryDirectory() as output_fqpn:
            print('created temporary directory', output_fqpn)
            read_ascii_huffman_table_from_file("../resources/csme12_huffmantable.txt")
            print("{0} entries in Huffman table".format(len(get_huffman_table())))
            main_run_for_packaged_compressed_file_input(output_fqpn, CSMEDecodeTests.file_input_v12.file, ["adspa"])
            adspa_decoded_truth_binary_fqpn = "../test_resources/v12_FTUP_adspa.decoded"
            adspa_decoded_decoder_output_fqpn = output_fqpn + "/FTUP/adspa.decoded"
            self.assertTrue(filecmp.cmp(adspa_decoded_truth_binary_fqpn, adspa_decoded_decoder_output_fqpn),
                            "The decoded (binary) output file for the 'adspa' code object from the v12 CSME binary "
                            "should be byte-equivalent to a known-to-be-correct raw binary version "
                            "of the 'adspa' code object")


if __name__ == '__main__':
    unittest.main()
