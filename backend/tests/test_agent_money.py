"""Exercise legacy agent deal math without importing optional Groq/OpenAI clients."""
import ast
import types
import unittest
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from pathlib import Path


class LegacyMoneyBoundaryTest(unittest.TestCase):
    def test_ten_percent_boundary_does_not_round_to_false_deal(self):
        source=(Path(__file__).resolve().parents[2]/'src'/'price_agent.py').read_text()
        tree=ast.parse(source)
        funcs=[node for node in tree.body if isinstance(node,ast.FunctionDef)
               and node.name in ('money','evaluate_deal')]
        namespace={'math':__import__('math'),'Decimal':Decimal,
                   'ROUND_HALF_UP':ROUND_HALF_UP,'AVG_FACTOR':0.90,
                   'LOW_FACTOR':1.05,'MIN_RATING':4.0,'MIN_SAMPLES':10,
                   'INFLATED_LIST_FACTOR':1.20}
        exec(compile(ast.Module(body=funcs,type_ignores=[]),'<deal_math>','exec'),namespace)
        state=types.SimpleNamespace(budget=1.0,
            fetched={'x':{'price':0.95,'list_price':1.0,
                          'seller_rating':4.5,'in_stock':True}},
            history={'x':{'avg_30d':1.05,'lowest_30d':0.95,'sample_count':30}})
        self.assertFalse(namespace['evaluate_deal'](state,'x')['checks']['below_average'])
        self.assertFalse(namespace['evaluate_deal'](state,'x')['genuine'])
        state.fetched['x']['price']=0.94
        self.assertTrue(namespace['evaluate_deal'](state,'x')['checks']['below_average'])

if __name__ == '__main__': unittest.main()
