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
import unittest

import bitstring

from decoder.csme_unpack import read_ascii_huffman_table_from_file, get_huffman_table, \
    get_shortest_huffman_code_in_nbits, get_longest_huffman_code_in_nbits, HuffmanTableEntry
from decoder.csme_unpack import clear_huffman_table_data


def get_longest_huffman_code_in_bits():
    pass


class HuffmanTableTests(unittest.TestCase):

    def setUp(self) -> None:
        clear_huffman_table_data()

    def test_read_ascii_huffman_table_v11_from_file(self):
        read_ascii_huffman_table_from_file("../resources/csme11_huffmantable.txt")
        self.assertEqual(len(get_huffman_table()), 1519, "Version 11 Huffman Table should have 1519 entries")
        self.assertEqual(get_shortest_huffman_code_in_nbits(), 7, "Version 11 Huffman Table's shortest entry (in "
                                                                  "number of bits) should be 7")
        self.assertEqual(get_longest_huffman_code_in_nbits(), 15, "Version 11 Huffman Table's longest entry (in "
                                                                  "number of bits) should be 15")

        # check some random entries for which there is a "truth table"
        self._check_huffman_table_random_entries("../test_resources/huffman_table_check_entries_v11.csv", "Version 11 "
                                                                                                          "Table")

    def test_read_ascii_huffman_table_v12_from_file(self):
        read_ascii_huffman_table_from_file("../resources/csme12_huffmantable.txt")
        self.assertEqual(len(get_huffman_table()), 1925, "Version 12 Huffman Table should have 1519 entries")
        self.assertEqual(get_shortest_huffman_code_in_nbits(), 7, "Version 12 Huffman Table's shortest entry (in "
                                                                  "number of bits) should be 7")
        self.assertEqual(get_longest_huffman_code_in_nbits(), 17, "Version 12 Huffman Table's longest entry (in "
                                                                  "number of bits) should be 17")
        # check some random entries for which there is a "truth table"
        self._check_huffman_table_random_entries("../test_resources/huffman_table_check_entries_v12.csv", "Version 12 "
                                                                                                          "Table")

    def _check_huffman_table_random_entries(self, truth_csv_file_fqpn, assert_message_tag: str):
        with open(truth_csv_file_fqpn, newline='') as cvsfile:
            reader = csv.reader(cvsfile)
            huffman_table = get_huffman_table()
            for dict1_str, dict2_str, length_str, depth_str, huffman_code in reader:
                huffman_code_bits = bitstring.ConstBitArray("0b" + str(huffman_code))

                dict1_bytes = bytearray((int(dict1_str)).to_bytes(int(length_str), "big"))
                dict2_bytes = bytearray(int(dict2_str).to_bytes(int(length_str), "big"))
                # check_hte = HuffmanTableEntry(int(dict1), int(dict2), int(length), int(depth), huffman_code)
                hte: HuffmanTableEntry = huffman_table.get(huffman_code_bits)
                self.assertIsNotNone(hte, ("" if assert_message_tag is None else assert_message_tag) +
                                     ": Huffman table should contain entry with huffman code " + str(huffman_code_bits))
                self.assertEqual(dict1_bytes, hte.dict1_value,
                                 ("" if assert_message_tag is None else assert_message_tag) +
                                 ": entry {0} has incorrect 'dictionary word' #1"
                                 .format(str(huffman_code_bits)))
                self.assertEqual(dict2_bytes, hte.dict2_value,
                                 ("" if assert_message_tag is None else assert_message_tag) +
                                 ": entry {0} has incorrect 'dictionary word' #2"
                                 .format(str(huffman_code_bits)))
                self.assertEqual(hte.huffman_code_rank, int(depth_str),
                                 ("" if assert_message_tag is None else assert_message_tag) +
                                 ": entry {0} is of incorrect 'depth'/'rank'".format(str(huffman_code_bits)))
                self.assertEqual(hte.dictionary_data_length, int(length_str),
                                 ("" if assert_message_tag is None else assert_message_tag) +
                                 ": entry {0} is of incorrect 'length' (number of bytes of the 'dictionary word')"
                                 .format(str(huffman_code_bits)))


if __name__ == '__main__':
    unittest.main()
