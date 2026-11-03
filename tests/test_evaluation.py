"""Independent oracle failures, public loading, and controlled reliability evidence."""

from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
from unittest.mock import patch

from scripts.prepare_data import prepare_sources
from scripts.prepare_demo import prepare_demo
from timbre.conversation import Conversation
from timbre.evaluation import Oracle, main, run_live, run_offline, scenarios
from timbre.llm.types import LLMEvent
from timbre.tools import ToolExecutor
from llm_support import OfflineTestCase, ScriptedClient, offline_config
from tests.support import DatabaseTestCase, FIXTURES, SimulatedAuthorizer


class EvaluationTests(DatabaseTestCase, OfflineTestCase):
    def setUp(self):
        super().setUp()
        OfflineTestCase.setUp(self)
        self.policies=self.directory/'policies.json'
        prepare_demo(self.database,self.policies)
        self.config=offline_config()
        self.config=replace(self.config,tools=replace(self.config.tools,database_path=str(self.database),policies_path=str(self.policies)))
        self.executor=ToolExecutor(self.database,self.policies)
        self.oracle=Oracle(self.database,self.policies)

    def test_demo_uses_same_importer_and_keeps_source_bytes(self):
        inputs=FIXTURES/'demo'
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir() if p.is_file()}
        report=prepare_demo(self.database,self.policies)
        self.assertEqual(report.total_records,22)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir() if p.is_file()})
        self.assertTrue(self.oracle.policies.document['name'].startswith('synthetic'))
        result=self.executor.execute('calculate_payment_options','{"product_id":101}').result
        self.assertEqual(result['status'],'success')
        self.assertTrue(all(c['passed'] for c in self.oracle.verify('calculate_payment_options',{'product_id':101},result)))

    def test_price_stock_and_sellability_fabrication_fail_independent_oracle(self):
        for field,value in (('price_brl','1.00'),('stock_quantity',999),('available',False)):
            result=self.executor.execute('get_product_details','{"product_id":101}').result
            result['data'][field]=value
            self.assertTrue(any(not c['passed'] for c in self.oracle.verify('get_product_details',{'product_id':101},result)))

    def test_wrong_policy_and_stacked_money_fail_oracle(self):
        result=self.executor.execute('get_store_policy','{"topic":"returns.online"}').result
        result['data']['sections'][0]['content']='Invented policy'
        self.assertTrue(any(not c['passed'] for c in self.oracle.verify('get_store_policy',{'topic':'returns.online'},result)))
        result=self.executor.execute('calculate_payment_options','{"product_id":101}').result
        result['data']['best_pix_option']['total_brl']='376.57'
        self.assertTrue(any(not c['passed'] for c in self.oracle.verify('calculate_payment_options',{'product_id':101},result)))

    def test_original_label_cannot_substitute_demo_for_takamine(self):
        with self.assertRaises(ValueError):
            scenarios(self.database,dataset='original')

    def test_offline_evaluation_never_calls_model_or_claims_answer_scores(self):
        result=run_offline(self.config,scenarios(self.database,dataset='synthetic'),'synthetic')
        self.assertEqual(len(result['results']),20)
        self.assertIsNone(result['model_metrics'])
        self.assertEqual(sum(r['status']=='pass' for r in result['results']),17)
        self.assertTrue(all('no model inference' in r['answer_review'] for r in result['results']))

    def test_fluent_ungrounded_live_response_fails_and_qualitative_review_is_unscored(self):
        scenario=[s for s in scenarios(self.database,dataset='synthetic') if s['id']=='E03']
        model=self.config.modes['standard'].model
        client=ScriptedClient([[LLMEvent(text='It costs R$1.00.',actual_model=model,finish_reason='stop')]])
        with patch('builtins.print'):
            report=run_live(client,self.config,scenario,['standard'],1,'synthetic')
        row=report['results'][0]
        self.assertEqual(row['status'],'fail')
        self.assertTrue(all(v is None for v in row['qualitative_review'].values()))
        self.assertIn('answer_exact_catalog_price',[c['check'] for c in row['checks'] if not c['passed']])

    def test_private_values_detected_without_echoing_them(self):
        self.assertFalse(self.oracle.no_private_disclosure('a@example.invalid'))
        self.assertTrue(self.oracle.no_private_disclosure('Please use verified support.'))

    def test_e17_owner_status_only_and_cross_owner_denial(self):
        authorizer=SimulatedAuthorizer()
        token=authorizer.issue_for_test(9001)
        executor=ToolExecutor(self.database,self.policies,authorizer=authorizer)
        own=executor.execute('get_my_order_status','{"order_id":5001}',context=token).result
        other=executor.execute('get_my_order_status','{"order_id":5002}',context=token).result
        self.assertEqual(own['status'],'success')
        self.assertNotIn('customer_id',own['data'])
        self.assertNotIn('phone',own['data'])
        self.assertEqual(other['status'],'empty')
        self.assertEqual(other['data'],{})

    def test_e20_interrupted_stream_keeps_history_and_records_error_once(self):
        client=ScriptedClient([[LLMEvent(text='Incomplete'),KeyboardInterrupt()]])
        conversation=Conversation(client,self.config,executor=self.executor,source='controlled_integration')
        before=conversation.history
        result=conversation.send('Synthetic interrupted request')
        self.assertEqual(result.metrics.status,'interrupted')
        self.assertEqual(before,conversation.history)
        self.assertEqual(len(conversation.observer.records),1)
        self.assertTrue(result.metrics.incomplete_stream)
        self.assertEqual(result.events[-1].event_type,'request_failed')

    def test_required_original_names_nested_input_missing_duplicate_and_overlap(self):
        source=self.directory/'source'
        (source/'data').mkdir(parents=True)
        for table in ('categories','products','customers','orders','order_items','promotions'):
            (source/'data'/f'desafio_tecnico_ai_eng - {table}.csv').write_bytes((FIXTURES/f'{table}.csv').read_bytes())
        for name in ('políticas_da_loja.pdf','desafio_tecnico_ai_eng_artefact.pdf'):
            (source/name).write_bytes(b'SYNTHETIC preparation test; not a real PDF')
        destination=self.directory/'prepared'
        hashes=prepare_sources(source,destination)
        self.assertEqual(len(hashes),8)
        self.assertTrue(all(hashlib.sha256((destination/n).read_bytes()).hexdigest()==h for n,h in hashes.items()))
        duplicate=source/'desafio_tecnico_ai_eng - products.csv'
        duplicate.write_bytes(b'Synthetic duplicate')
        with self.assertRaises(ValueError): prepare_sources(source,self.directory/'not-created')
        self.assertFalse((self.directory/'not-created').exists())
        duplicate.unlink()
        (source/'políticas_da_loja.pdf').unlink()
        with self.assertRaises(ValueError): prepare_sources(source,self.directory/'not-created')
        # Every destination is checked before any write, even if overlap is last.
        (source/'políticas_da_loja.pdf').write_bytes(b'SYNTHETIC policy')
        before=(source/'desafio_tecnico_ai_eng_artefact.pdf').read_bytes()
        with self.assertRaises(ValueError): prepare_sources(source,source)
        self.assertFalse((source/'desafio_tecnico_ai_eng - categories.csv').exists())
        self.assertEqual(before,(source/'desafio_tecnico_ai_eng_artefact.pdf').read_bytes())


if __name__=='__main__':
    import unittest
    unittest.main()
